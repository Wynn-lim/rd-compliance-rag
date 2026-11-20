"""中文检索分词：保护文号 / M 编号 / E 编号等高信号 token，其余用 jieba 切词。"""
import re

import jieba

jieba.setLogLevel(20)

# 需要整体保护、不拆开的模式
PROTECT_PATTERNS = [
    r"[一-龥A-Za-z]{2,14}\s*〔\s*\d{4}\s*〕\s*\d+\s*号",     # 财税〔2015〕119 号
    r"(?:公告|令|函)\s*\d{4}\s*年\s*第\s*\d+\s*号",          # 2023 年第 7 号
    r"\bM\d{2}(?:-\d{2}){0,2}\b",                            # M06-15
    r"\bE-\d{3}\b",                                          # E-002
    r"\b\d+(?:\.\d+)?\s*(?:%|％|万元|亿元|天|年|个月|月|日)\b",  # 120%、183 天
    r"\b[A-Z]{2}\b",                                         # 铁律 AA—IZ / IPO / CAS / R&D
]
PROTECT_RE = re.compile("(" + "|".join(PROTECT_PATTERNS) + ")")

STOPWORDS = set("""
的 了 是 在 我 你 他 她 它 们 这 那 和 与 及 或 而 并 且 但 就是 不是 没有 一个 一些
什么 怎么 怎样 如何 能不能 可以 是否 能否 多少 几 哪个 哪些 请问 一下 我们 你们 他们
吗 呢 吧 啊 呀 哦 嗯 如果 因为 所以 虽然 但是 然后 现在 目前 以及 对于 关于 根据 按照
按 依 据 从 到 向 被 把 让 使 该 此 本 各 每 某 其 之 于 以 为 所 然 后 前 中 间 内 外
上 下 左 右 大 小 多 少 高 低 新 旧 好 坏 对 错 真 假 有 无 未 已 才 就 还 又 也 都
很 太 更 最 较 极 常 往 昔 今 明 去 来 回 起 过 出 入 成 败 功 过
""".split())

CJK_RE = re.compile(r"[一-龥]")
ALNUM_RE = re.compile(r"[A-Za-z0-9]")


def _normalize(text):
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _cut(segment):
    """对非保护片段做 jieba 切分与停用词过滤。"""
    out = []
    for w in jieba.lcut(segment):
        w = w.strip()
        if not w or w in STOPWORDS:
            continue
        if CJK_RE.search(w):
            if len(w) == 1 and w not in ("税", "费", "票", "账", "表", "据"):
                continue
            out.append(w)
        elif ALNUM_RE.search(w):
            out.append(w.lower())
    return out


def tokenize(text):
    """返回 token 列表。文号 / M 编号 / E 编号 / 百分比等整体保护，不拆开。

    做法是按保护模式把文本切开：保护片段原样成一个 token，
    其余片段才交给 jieba——避免占位符被分词器打散。
    """
    if not text:
        return []
    text = _normalize(text)
    tokens, pos = [], 0
    for m in PROTECT_RE.finditer(text):
        tokens.extend(_cut(text[pos:m.start()]))
        tokens.append(re.sub(r"\s+", "", m.group(0)).lower())
        pos = m.end()
    tokens.extend(_cut(text[pos:]))
    return tokens


def bigrams(tokens):
    """在词序列后追加相邻二字组，提升中文召回（专有名词常被切碎）。"""
    out = list(tokens)
    for a, b in zip(tokens, tokens[1:]):
        if len(a) >= 2 and len(b) >= 2:
            out.append(a[-1] + b[0])
    return out
