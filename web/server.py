"""单页问答服务（Python 标准库，无框架依赖）。

    python -I web/server.py --port 8000                 # 仅本机
    python -I web/server.py --host 0.0.0.0 --port 8000  # 同一局域网内可访问
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR.parent))

from rag import llm as llm_mod  # noqa: E402
from rag.config import LAYER_LABEL  # noqa: E402
from rag.pipeline import answer  # noqa: E402

# ---------- 局域网访问控制 ----------
# 知识库含客户案例与 IPO 问询细节，开放到局域网前必须有一道门。
# 账号密码在 web/auth.json，改完重启生效；该文件不进版本库。
AUTH_FILE = WEB_DIR / "auth.json"
PUBLIC_PATHS = ("/login", "/logout", "/api/health")
COOKIE_NAME = "rdkb_session"


def load_auth():
    cfg = {
        "enabled": True,
        "username": "zhishi",
        "password": "kb2026",
        "session_secret": secrets.token_hex(32),
    }
    try:
        cfg.update(json.loads(AUTH_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


AUTH = load_auth()


def _token(user):
    return hmac.new(
        AUTH["session_secret"].encode("utf-8"), user.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]


def is_authed(headers):
    if not AUTH.get("enabled", True):
        return True
    m = re.search(COOKIE_NAME + r"=([a-f0-9]+)", headers.get("Cookie", "") or "")
    return bool(m) and hmac.compare_digest(m.group(1), _token(AUTH["username"]))


LOGIN_PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>登录 · 研发合规知识库</title>
<style>
:root{--ink-0:#0E1319;--ink-1:#151B24;--line:#28323E;--paper:#E6E2D9;
  --dim:#9AA3AE;--faint:#66707C;--seal:#C8442E}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:var(--ink-0);color:var(--paper);
  font:13.5px/1.75 "PingFang SC","Microsoft YaHei",system-ui,sans-serif;
  display:grid;place-items:center;padding:24px}
.box{width:100%;max-width:360px;background:var(--ink-1);border:1px solid var(--line);
  border-radius:2px;padding:30px 28px}
.seal{width:38px;height:38px;border:1.5px solid var(--seal);border-radius:2px;
  display:grid;place-items:center;font-family:SimSun,serif;font-size:20px;
  color:var(--seal);font-weight:700;margin-bottom:16px}
h1{font-family:SimSun,serif;font-size:17px;margin:0 0 4px;font-weight:700}
.sub{color:var(--faint);font-size:12px;margin:0 0 22px}
label{display:block;font-size:11.5px;color:var(--dim);margin:12px 0 5px}
input{width:100%;border:1px solid var(--line);border-radius:2px;background:var(--ink-0);
  color:var(--paper);padding:9px 11px;font:13px inherit}
input:focus{outline:none;border-color:var(--seal)}
button{width:100%;margin-top:20px;border:1px solid var(--seal);background:var(--seal);
  color:#fff;border-radius:2px;padding:10px;font:600 13px inherit;cursor:pointer}
button:hover{background:#D6543C}
.err{color:var(--seal);font-size:12px;margin-top:14px;padding:8px 11px;
  border:1px solid rgba(200,68,46,.35);border-radius:2px;background:rgba(200,68,46,.08)}
.foot{color:var(--faint);font-size:11px;margin-top:18px;text-align:center;line-height:1.7}
</style></head><body>
<div class="box">
  <div class="seal">研</div>
  <h1>研发合规与研发费用管理知识库</h1>
  <p class="sub">内网检索服务 · 需登录后使用</p>
  {ERROR}
  <form method="post" action="/login">
    <input type="hidden" name="next" value="{NEXT}">
    <label for="u">账号</label>
    <input id="u" name="username" autocomplete="username" required autofocus>
    <label for="p">密码</label>
    <input id="p" name="password" type="password" autocomplete="current-password" required>
    <button type="submit">登录</button>
  </form>
  <p class="foot">库内含客户案例与 IPO 问询细节<br>请勿外传，用后请退出登录</p>
</div></body></html>"""

_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "RDRAG/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[web] %s\n" % (fmt % args))

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("location", location)
        self.send_header("content-length", "0")
        self.end_headers()

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_login(self):
        try:
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length).decode("utf-8", "replace")
            form = dict(p.split("=", 1) for p in body.split("&") if "=" in p)
            from urllib.parse import unquote_plus

            user = unquote_plus(form.get("username", ""))
            pwd = unquote_plus(form.get("password", ""))
            nxt = unquote_plus(form.get("next", "/")) or "/"
            if not nxt.startswith("/"):
                nxt = "/"
        except Exception:
            self._send_html(LOGIN_PAGE.replace("{ERROR}",
                '<div class="err">请求格式有误，请重试。</div>').replace("{NEXT}", "/"), 400)
            return

        ok = (
            hmac.compare_digest(user, str(AUTH.get("username", "")))
            and hmac.compare_digest(pwd, str(AUTH.get("password", "")))
        )
        if not ok:
            self._send_html(LOGIN_PAGE.replace("{ERROR}",
                '<div class="err">账号或密码不对。</div>').replace("{NEXT}", nxt), 401)
            return

        self.send_response(302)
        self.send_header("location", nxt)
        self.send_header(
            "set-cookie",
            f"{COOKIE_NAME}={_token(AUTH['username'])}; Path=/; HttpOnly; SameSite=Lax",
        )
        self.send_header("content-length", "0")
        self.end_headers()

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, ctype):
        try:
            body = path.read_bytes()
        except OSError:
            self._send_json({"error": "not found"}, 404)
            return
        self.send_response(200)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/login":
            self._send_html(LOGIN_PAGE.replace("{ERROR}", "").replace("{NEXT}", "/"))
            return
        if path == "/logout":
            self.send_response(302)
            self.send_header("location", "/login")
            self.send_header("set-cookie", f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly")
            self.send_header("content-length", "0")
            self.end_headers()
            return
        if path not in PUBLIC_PATHS and not is_authed(self.headers):
            if path.startswith("/api/"):
                self._send_json({"error": "未登录", "hint": "请先打开首页登录"}, 401)
            else:
                self._redirect("/login")
            return
        if path in ("/", "/index.html"):
            self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
        elif path == "/api/health":
            self._send_json({"ok": True, "backends": llm_mod.available_backends(),
                             "auth": bool(AUTH.get("enabled", True))})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/login":
            self._handle_login()
            return
        if path == "/logout":
            self.send_response(302)
            self.send_header("location", "/login")
            self.send_header("set-cookie", f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly")
            self.send_header("content-length", "0")
            self.end_headers()
            return
        if path not in PUBLIC_PATHS and not is_authed(self.headers):
            self._send_json({"error": "未登录", "hint": "请先打开首页登录"}, 401)
            return
        if path not in ("/api/ask", "/api/prompt"):
            self._send_json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("content-length", 0))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception as e:
            self._send_json({"error": f"bad request: {e}"}, 400)
            return

        query = (payload.get("query") or "").strip()
        if not query:
            self._send_json({"error": "query 不能为空"}, 400)
            return

        top_k = int(payload.get("top_k", 6))
        use_dense = bool(payload.get("dense", True))

        try:
            with _lock:
                res = answer(query, top_k=top_k, backend="none",
                             with_dense=use_dense, export_prompt=True)
        except Exception as e:
            self._send_json({"error": f"{type(e).__name__}: {e}"}, 500)
            return

        if path == "/api/prompt":
            body = res["prompt"].encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        backend = payload.get("backend") or "none"

        # 先查后端是否可用，避免把裸异常抛给前端
        ok, hint = llm_mod.backend_ready(backend)
        if not ok:
            self._send_json({
                "error": "LLM 未配置",
                "hint": hint,
                "query": query,
                "retrieval": {"layers": [], "latency_ms": 0, "dense": use_dense,
                              "rerank": False, "relevant": None, "relevance_reason": ""},
                "sources": [],
                "errata_warnings": [],
            }, 400)
            return

        try:
            with _lock:
                res = answer(query, top_k=top_k, backend=backend,
                             history=payload.get("history") or [], with_dense=use_dense)
        except llm_mod.LLMError as e:
            self._send_json({"error": "LLM 调用失败", "hint": str(e),
                             "query": query}, 502)
            return
        except Exception as e:
            self._send_json({"error": f"{type(e).__name__}: {e}"}, 500)
            return

        self._send_json({
            "query": query,
            "answer": res.get("answer"),
            "backend": res.get("backend"),
            "prompt_available": bool(res.get("prompt")),
            "retrieval": res["retrieval"],
            "sources": [
                {
                    "n": s["n"],
                    "layer": s["layer"],
                    "layer_label": LAYER_LABEL.get(s["layer"], s["layer"]),
                    "rel_path": s["rel_path"],
                    "m_code": s["m_code"],
                    "e_code": s["e_code"],
                    "section": s["section"],
                    "status": s["status"],
                    "doc_ids": s["doc_ids"],
                    "score": s["score"],
                    "chars": s["chars"],
                    "text": s.get("text", ""),
                }
                for s in res["sources"]
            ],
            "errata_warnings": [
                {
                    "e_code": w["e_code"],
                    "rel_path": w["rel_path"],
                    "section": w["section"],
                    "score": w["score"],
                    "chars": w["chars"],
                    "text": w["text"],
                }
                for w in res.get("errata_warnings", [])
            ],
        })


def _lan_ips():
    """枚举本机私网 IPv4（排除回环、链路本地与虚拟网卡常见段）。"""
    import socket

    cands = set()
    # 途径一：默认路由所用网卡
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        cands.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    # 途径二：本机所有网卡
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            cands.add(info[4][0])
    except Exception:
        pass

    def is_private(ip):
        if ip.startswith("127.") or ip.startswith("169.254."):
            return False
        if ip.startswith("192.168."):
            return True
        if ip.startswith("10."):
            return True
        if ip.startswith("172."):
            try:
                return 16 <= int(ip.split(".")[1]) <= 31
            except ValueError:
                return False
        return False

    priv = sorted(ip for ip in cands if is_private(ip))
    # 198.18.x / 198.19.x 是基准测试保留段，多为虚拟网卡，排到最后
    priv.sort(key=lambda ip: (ip.startswith("198."), ip))
    return priv


def main():
    ap = argparse.ArgumentParser(
        description="研发合规知识库问答服务。默认只听本机；"
                    "要让同一 WiFi 的人也能用，加 --host 0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default=os.environ.get("RAG_HOST", "127.0.0.1"),
                    help="绑定地址。127.0.0.1=仅本机；0.0.0.0=同一局域网内可访问")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    lan = ""
    if args.host == "0.0.0.0":
        lan = "　同一 WiFi 内访问：" + "  ".join(
            f"http://{ip}:{args.port}" for ip in _lan_ips()
        ) or "　同一 WiFi 内访问：http://<你的内网IP>:" + str(args.port)
    print(f"服务已启动：http://{args.host}:{args.port}{lan}")
    print("可用 LLM backend：", llm_mod.available_backends())
    print("按 Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
