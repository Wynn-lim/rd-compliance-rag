"""单独对比：开/关重排的效果与延迟。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from rag.pipeline import get_retriever  # noqa: E402

QS = [
    ("BC-02", "新版《高新技术企业认定管理办法》是否已发布？发明专利权重是否提到 45%～50%？"),
    ("BC-04", "研发费用监管有哪几个口径？"),
    ("Q6", "研发支出资本化的五个条件是什么？"),
    ("Q1", "研发费用加计扣除现在的比例是多少？未形成无形资产、形成无形资产分别怎么处理？"),
]


def main():
    r = get_retriever(with_dense=True)
    print("reranker available:", r._reranker_ok, flush=True)
    for qid, q in QS:
        for use_rr in (False, True):
            t0 = time.time()
            res, warns, info = r.search(q, top_k=8, use_dense=True, explain=True, use_rerank=use_rr)
            dt = time.time() - t0
            ecodes = [x["e_code"] for x in (res + warns) if x["e_code"]]
            top = [
                (x["m_code"] or x["e_code"] or Path(x["rel_path"]).name[:10], x.get("cross_score"))
                for x in res[:4]
            ]
            print(f"{qid} rerank={use_rr} {dt:.1f}s | E:{ecodes[:4]}", flush=True)
            print("    top4:", top, flush=True)


if __name__ == "__main__":
    main()
