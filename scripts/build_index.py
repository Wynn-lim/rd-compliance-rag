"""构建分块 + BM25 词表 + 向量索引。

用法：
    python -I scripts/build_index.py                 # 用默认模型
    RAG_DENSE_MODEL=BAAI/bge-small-zh-v1.5 python -I scripts/build_index.py
    python -I scripts/build_index.py --rebuild       # 强制重建分块
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.config import DENSE_MODEL  # noqa: E402
from rag.dense import encode, get_encoder  # noqa: E402
from rag.store import (  # noqa: E402
    build_or_load_chunks,
    build_tokens,
    save_chunks,
    save_embeddings,
    save_tokens,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="强制重建分块")
    ap.add_argument("--no-dense", action="store_true", help="只建 BM25，不建向量")
    ap.add_argument("--batch", type=int, default=16)
    args = ap.parse_args()

    t0 = time.time()
    if args.rebuild:
        from rag.chunker import build_chunks
        from rag.config import EXCLUDED_DIRS, GOVERNANCE_FILES, KB_ROOT, KNOWLEDGE_DIRS

        chunks = build_chunks(KB_ROOT, GOVERNANCE_FILES, KNOWLEDGE_DIRS, EXCLUDED_DIRS)
        save_chunks(chunks)
    else:
        chunks = build_or_load_chunks(rebuild=False)
    print(f"[1/3] chunks: {len(chunks)}  ({time.time() - t0:.1f}s)")

    tokens = build_tokens(chunks)
    save_tokens(tokens)
    print(f"[2/3] tokens saved  ({time.time() - t0:.1f}s)")

    if args.no_dense:
        print("skip dense (--no-dense)")
        return

    model = get_encoder(DENSE_MODEL)
    print(f"[3/3] encoding with {DENSE_MODEL} ...")
    texts = [c["text"] for c in chunks]
    mat = encode(model, texts, batch_size=args.batch, normalize=True)
    save_embeddings(mat)
    print(f"[3/3] embeddings {mat.shape} saved  (total {time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
