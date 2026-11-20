"""导出静态演示数据：跑一遍检索，把结果写成 demo/data/results.json。

公开仓库里只能放**脱敏后**的纯政策内容，所以导出后会自动扫描敏感词，
命中即整块丢弃，终检再扫一遍——不靠人工把关。

敏感词表在 scripts/sensitive_words.txt（**已 gitignore，不进仓库**）。
它是运营知识而不是代码：公开它等于把要保护的对象列给人看。
词表缺失时本脚本拒绝运行（fail closed），不会静默放行。

    python -I scripts/export_demo.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from rag.pipeline import get_retriever  # noqa: E402

WORDS_FILE = Path(__file__).resolve().parent / "sensitive_words.txt"

# ---- 精选问题：全部是纯政策问题，不含任何客户情境 ----
QUESTIONS = [
    {"id": "Q1", "q": "研发费用加计扣除现在的比例是多少？未形成无形资产、形成无形资产分别怎么处理？",
     "note": "比例与摊销"},
    {"id": "Q2", "q": "集成电路和工业母机企业的加计扣除比例是多少？到什么时候？",
     "note": "特殊行业时限"},
    {"id": "Q3", "q": "委托境内研发的加计基数是多少？委托境外呢？",
     "note": "委外基数"},
    {"id": "Q4", "q": "高企认定研发费用占销售收入比例分几档？",
     "note": "高企占比"},
    {"id": "Q5", "q": "研发支出资本化的五个条件是什么？",
     "note": "资本化五条件"},
    {"id": "Q6", "q": "委托研发的「知识产权归属」是不是加计扣除的门槛？",
     "note": "假闸辨析"},
    {"id": "Q7", "q": "加计扣除的行业负面清单有哪些？",
     "note": "负面清单"},
    {"id": "Q8", "q": "研发费用监管有哪几个口径？",
     "note": "五口径"},
    {"id": "Q9", "q": "「集中研发」的加计条文在哪里？",
     "note": "条文定位"},
    {"id": "Q10", "q": "2026 年制造业企业研发费用加计扣除比例是不是已提高到 120%？",
     "note": "抗污染实测"},
]

EXCERPT_CHARS = 900


def load_forbidden():
    if not WORDS_FILE.exists():
        sys.stdout.reconfigure(encoding="utf-8")
        print("[拒绝运行] 缺少敏感词表：", WORDS_FILE)
        print("该文件是运营知识，按设计不进版本库。请本地创建，一行一个词。")
        print("每行写一个需要屏蔽的词（企业名、内部流程用语、发行审核用语等）。")
        raise SystemExit(1)
    words = [
        ln.strip()
        for ln in WORDS_FILE.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not words:
        print("[拒绝运行] 敏感词表为空：", WORDS_FILE)
        raise SystemExit(1)
    return words


FORBIDDEN = load_forbidden()


def scan(text):
    hits = [w for w in FORBIDDEN if w in text]
    return hits


def keep(x, dropped, kind):
    """单块过滤：命中敏感词则记入 dropped 并返回 None。"""
    hits = scan(x["text"]) + scan(x.get("section") or "")
    if hits:
        dropped.append({"kind": kind, "id": x.get("m_code") or x.get("e_code"),
                        "section": (x.get("section") or "")[:40], "hits": hits})
        return None
    return x


def trim(x):
    y = dict(x)
    y["text"] = y["text"][:EXCERPT_CHARS]
    return y


def main():
    r = get_retriever(with_dense=True)
    out, dropped = [], []
    for item in QUESTIONS:
        res, warns, info = r.search(item["q"], top_k=6, use_dense=True, explain=True)

        sources = [s for s in (keep(x, dropped, "正文") for x in res) if s]
        warnings = [w for w in (keep(x, dropped, "纠错") for x in warns) if w]
        if len(sources) < 2:
            print(f"  [跳过] {item['id']} 脱敏后仅剩 {len(sources)} 条正文，不足 2 条，不收录")
            continue

        out.append({
            "id": item["id"],
            "q": item["q"],
            "note": item["note"],
            "retrieval": {
                "layers": sorted(info["layers"]),
                "main_layers": sorted(info["main_layers"]),
                "reasons": info["reasons"],
                "route_codes": info.get("route_codes", []),
                "candidates": info["candidates"],
                "fused": info["fused"],
                "dense": True,
                "errata_primary": info.get("errata_primary", False),
            },
            "sources": [
                {
                    "n": i,
                    "layer": x["layer"],
                    "rel_path": x["rel_path"],
                    "m_code": x["m_code"],
                    "e_code": x["e_code"],
                    "section": x["section"],
                    "status": x["status"],
                    "doc_ids": x["doc_ids"],
                    "score": x["score"],
                    "chars": x["chars"],
                    "text": trim(x)["text"],
                }
                for i, x in enumerate(sources, start=1)
            ],
            "errata_warnings": [
                {
                    "e_code": x["e_code"],
                    "rel_path": x["rel_path"],
                    "section": x["section"],
                    "score": x["score"],
                    "chars": x["chars"],
                    "text": trim(x)["text"],
                }
                for x in warnings
            ],
        })

    if not out:
        print("[拒绝导出] 脱敏后没有任何可收录的问题。")
        raise SystemExit(1)

    # ---- 终检：整份 JSON 再扫一遍，不靠人工放行 ----
    hits = scan(json.dumps(out, ensure_ascii=False))
    if hits:
        print("[拒绝导出] 终检仍检出敏感内容：", hits)
        raise SystemExit(1)

    dest = Path(__file__).resolve().parent.parent / "demo" / "data"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    total = sum(len(e["sources"]) + len(e["errata_warnings"]) for e in out)
    print(f"OK 导出 {len(out)} 题，{total} 条内容，"
          f"{(dest / 'results.json').stat().st_size // 1024} KB，终检通过")
    print(f"脱敏丢弃 {len(dropped)} 块：")
    for d in dropped[:15]:
        print(f"   {d['kind']} {d['id']} | {d['section']} | 命中 {d['hits']}")


if __name__ == "__main__":
    main()
