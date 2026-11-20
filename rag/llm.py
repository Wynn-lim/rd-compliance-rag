"""可插拔 LLM 后端。

backend:
  - "none"    ：不调用模型，返回检索报告 + 完整 prompt（当前环境无可用 key 时的默认）
  - "anthropic"：Anthropic Messages API（读 ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL）
  - "openai"  ：任意 OpenAI 兼容端点（DeepSeek / Qwen / vLLM / Ollama，读 OPENAI_* 变量）

密钥一律从环境变量读取，不写入任何文件（项目既有纪律）。
"""
import json
import os
import urllib.error
import urllib.request


class LLMError(RuntimeError):
    pass


def backend_ready(backend):
    """检查后端是否可用。返回 (ok, 给人看的提示)。

    "none" 是合法模式（只检索、导出 prompt），算可用。
    """
    if backend in (None, "none"):
        return True, ""
    if backend == "anthropic":
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return True, ""
        return False, (
            "选了 Anthropic 但没设 key。在启动服务的同一个终端里先执行：\n"
            "  set ANTHROPIC_API_KEY=sk-ant-...\n"
            "然后重启服务。"
        )
    if backend == "openai":
        if os.environ.get("OPENAI_API_KEY"):
            return True, ""
        return False, (
            "选了 OpenAI 兼容但没设 key。在启动服务的同一个终端里先执行：\n"
            "  set OPENAI_API_KEY=sk-...\n"
            "  set OPENAI_BASE_URL=https://api.deepseek.com/v1\n"
            "（国内可用 DeepSeek；用别的平台就换对应的 BASE_URL）\n"
            "然后重启服务。"
        )
    return False, f"未知后端：{backend}"


def available_backends():
    out = ["none"]
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        out.insert(0, "anthropic")
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_BASE_URL"):
        out.insert(0, "openai")
    return out


def _post(url, headers, payload, timeout=180):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise LLMError(f"HTTP {e.code} from {url}: {body}") from e
    except Exception as e:
        raise LLMError(f"{type(e).__name__}: {e}") from e


def chat_anthropic(messages, model=None, max_tokens=2000, temperature=0.1):
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if not key:
        raise LLMError("未设置 ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN")
    base = (os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
    model = model or os.environ.get("RAG_LLM_MODEL") or "claude-sonnet-5"
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    msgs = [m for m in messages if m["role"] != "system"]
    data = _post(
        f"{base}/v1/messages",
        {"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"},
        {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": msgs,
        },
    )
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def chat_openai(messages, model=None, max_tokens=2000, temperature=0.1):
    key = os.environ.get("OPENAI_API_KEY", "")
    base = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = model or os.environ.get("RAG_LLM_MODEL") or "deepseek-chat"
    data = _post(
        f"{base}/chat/completions",
        {"content-type": "application/json", "authorization": f"Bearer {key}"},
        {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        },
    )
    return data["choices"][0]["message"]["content"]


def generate(messages, backend=None, **kw):
    backend = backend or os.environ.get("RAG_LLM_BACKEND") or "none"
    if backend == "none":
        raise LLMError("backend=none：不调用模型（检索模式）")
    if backend == "anthropic":
        return chat_anthropic(messages, **kw)
    if backend == "openai":
        return chat_openai(messages, **kw)
    raise LLMError(f"未知 backend: {backend}")
