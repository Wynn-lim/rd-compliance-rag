"""分块与索引的持久化（jsonl + json + npy，不用 pickle）。"""
import json

import numpy as np

from .chunker import build_chunks
from .config import DATA_DIR, EXCLUDED_DIRS, GOVERNANCE_FILES, KB_ROOT, KNOWLEDGE_DIRS
from .tokenizer import bigrams, tokenize


def chunks_path():
    return DATA_DIR / "chunks.jsonl"


def save_chunks(chunks):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with chunks_path().open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def load_chunks():
    out = []
    with chunks_path().open(encoding="utf-8") as f:
        for line in f:
            out.append(json.loads(line))
    return out


def build_or_load_chunks(rebuild=False):
    if chunks_path().exists() and not rebuild:
        return load_chunks()
    chunks = build_chunks(KB_ROOT, GOVERNANCE_FILES, KNOWLEDGE_DIRS, EXCLUDED_DIRS)
    save_chunks(chunks)
    return chunks


def build_tokens(chunks):
    return [bigrams(tokenize(c["text"])) for c in chunks]


def save_tokens(tokens, name="tokens.json"):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (DATA_DIR / name).open("w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False)


def load_tokens(name="tokens.json"):
    with (DATA_DIR / name).open(encoding="utf-8") as f:
        return json.load(f)


def save_embeddings(mat, name="embeddings.npy"):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    np.save(DATA_DIR / name, mat.astype(np.float32))


def load_embeddings(name="embeddings.npy"):
    return np.load(DATA_DIR / name)
