"""bge-m3 向量检索（numpy 余弦，懒加载模型）。"""
import numpy as np

_encoder = None


def get_encoder(model_name):
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer

        _encoder = SentenceTransformer(model_name)
    return _encoder


def encode(model, texts, batch_size=16, normalize=True):
    if isinstance(texts, str):
        texts = [texts]
    vecs = model.encode(
        texts, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=normalize
    )
    return np.asarray(vecs, dtype=np.float32)


def cosine_top_k(query_vec, matrix, k, candidate_idx=None):
    if candidate_idx is None:
        sims = matrix @ query_vec
        idx = np.argpartition(-sims, min(k, len(sims) - 1))[:k]
        return [(int(i), float(sims[i])) for i in idx]
    sub = matrix[candidate_idx]
    sims = sub @ query_vec
    k = min(k, len(sims))
    order = np.argpartition(-sims, k - 1)[:k]
    return [(int(candidate_idx[j]), float(sims[j])) for j in order]
