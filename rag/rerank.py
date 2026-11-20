"""交叉编码器重排（bge-reranker）。

混合检索解决「召回」，重排解决「排对」。政策问句里同一篇文章常有十几个节，
只有重排能稳定把「讲那件事的那一节」排到最前。
"""
import os

_reranker = None


def reranker_available(model_name=None):
    """只查本地缓存，**不触发下载**。没下过就返回 False，系统自动降级。"""
    name = model_name or os.environ.get("RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    try:
        from huggingface_hub import try_to_load_from_cache

        refs = try_to_load_from_cache(name, "config.json")
        if isinstance(refs, str):
            return True
        # 有些仓库只有 pytorch_model.bin / model.safetensors
        for f in ("config_sentence_transformers.json", "modules.json", "tokenizer_config.json"):
            r = try_to_load_from_cache(name, f)
            if isinstance(r, str):
                return True
        return False
    except Exception:
        return False


def get_reranker(model_name=None):
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(
            model_name or os.environ.get("RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
            max_length=1024,
        )
    return _reranker


def rerank(model, query, texts, batch_size=8):
    """返回与 texts 等长的分数数组（越高越相关）。"""
    if not texts:
        return []
    pairs = [(query, t) for t in texts]
    scores = model.predict(pairs, batch_size=batch_size, show_progress_bar=False)
    return [float(s) for s in scores]
