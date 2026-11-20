import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from rag.pipeline import get_retriever  # noqa: E402
from rag.tokenizer import bigrams, tokenize  # noqa: E402


def main():
    r = get_retriever(with_dense=True)
    cases = [
        ("BC-02", "新版《高新技术企业认定管理办法》是否已发布？发明专利权重是否提到 45%～50%？", "E-003"),
        ("BC-04", "研发费用监管有哪几个口径？", "E-005"),
    ]
    for qid, q, tgt in cases:
        res, warns, info = r.search(q, top_k=8, use_dense=True, explain=True, use_rerank=False)
        print("==", qid, "errata warnings:")
        for x in warns:
            print("   ", x["e_code"], round(x["dense_sim"], 3), round(x["bm25_score"], 1), x["section"][:36])
        qv = r._query_vec(q)
        qt = bigrams(tokenize(q))
        for idx, c in enumerate(r.chunks):
            if c.get("e_code") == tgt:
                print(f"   TARGET {tgt}: dense={float(r.emb[idx] @ qv):.3f} "
                      f"bm25={r.bm25.score(qt, idx):.1f} chars={c['chars']}")
                print("   TARGET head:", c["text"][:120].replace("\n", " "))
                break


if __name__ == "__main__":
    main()
