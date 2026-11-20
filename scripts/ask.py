"""命令行问答。

    python -I scripts/ask.py "研发费用加计扣除比例是多少？"
    python -I scripts/ask.py --explain "这个问题"
    python -I scripts/ask.py --no-dense "这个问题"
    python -I scripts/ask.py --backend anthropic "这个问题"     # 设了 key 才可用
    python -I scripts/ask.py --dump-prompt "这个问题" > prompt.txt
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from rag import llm as llm_mod  # noqa: E402
from rag.config import LAYER_LABEL  # noqa: E402
from rag.pipeline import answer  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="+")
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--no-dense", action="store_true")
    ap.add_argument("--no-llm", action="store_true", help="只做检索（默认即无 key 时的行为）")
    ap.add_argument("--backend", default=None, help="anthropic / openai / none")
    ap.add_argument("--dump-prompt", action="store_true", help="导出完整 prompt 后退出")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    query = " ".join(args.query)
    backend = "none" if (args.no_llm or args.dump_prompt) else args.backend

    res = answer(
        query,
        top_k=args.top_k,
        backend=backend,
        with_dense=not args.no_dense,
        export_prompt=args.dump_prompt,
    )

    if args.dump_prompt:
        print(res["prompt"])
        return
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    print(f"\n问题：{query}")
    print(f"检索层：{', '.join(res['retrieval']['layers'])}  |  向量: "
          f"{'开' if res['retrieval']['dense'] else '关'}  |  耗时 {res['retrieval']['latency_ms']} ms")
    if args.explain:
        for reason in res["retrieval"]["reasons"]:
            print(f"  · {reason}")
        if res["retrieval"]["route_codes"]:
            print(f"  · 路由反推条目: {', '.join(res['retrieval']['route_codes'][:10])}")

    print("\n--- 检索到的出处 ---")
    for s in res["sources"]:
        tag = f"[{s['n']}] {LAYER_LABEL.get(s['layer'], s['layer'])}"
        code = s["m_code"] or s["e_code"] or Path(s["rel_path"]).name
        print(f"{tag} {code}｜{s['section'][:30]}｜{s['chars']} 字｜score {s['score']}")
        print(f"     {s['rel_path']}")

    print("\n--- 回答 ---")
    if res.get("answer"):
        print(res["answer"])
    else:
        print("（未配置 LLM，以下为可直接使用的完整 prompt；"
              "设置 ANTHROPIC_API_KEY 或 OPENAI_API_KEY/BASE_URL 后加 --backend 即可自动生成）")
        print("可用 backend：", llm_mod.available_backends())
        print(res["prompt"])


if __name__ == "__main__":
    main()
