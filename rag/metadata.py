"""从 markdown 文本中提取结构化元数据：M/E 编号、政策文号、状态等级、日期。"""
import re

# ---- M 编号 / E 编号 ----
M_CODE_RE = re.compile(r"\bM(\d{2})(?:-(\d{2}))?(?:-(\d{2}))?\b")
E_CODE_RE = re.compile(r"\bE-(\d{3})\b")

# ---- 政策文号 ----
# 括号式：财税〔2015〕119 号 / 国科发火〔2016〕32 号 / 证监会公告〔2024〕6 号
DOC_BRACKET_RE = re.compile(
    r"[一-龥A-Za-z]{2,14}\s*〔\s*(\d{4})\s*〕\s*(\d+)\s*号"
)
# 公告式：财政部 税务总局公告 2023 年第 7 号 / 国家税务总局公告 2017 年第 40 号
DOC_ANNOUNCE_RE = re.compile(
    r"(?:公告|令|函)\s*(\d{4})\s*年\s*第\s*(\d+)\s*号"
)
# 令式：国务院令第 797 号
DOC_ORDER_RE = re.compile(r"令\s*第\s*(\d+)\s*号")
# 财办会〔2026〕35 号 之类已被括号式覆盖

STATUS_RE = re.compile(r"[✅🟢🟡🔴⚠️]\s*\*{0,2}(L[0-4])")
DATE_RE = re.compile(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})")


def normalize_doc(bracket_match=None, announce_match=None):
    out = []
    for m in (bracket_match, announce_match):
        if m:
            out.append(f"{m.group(1)}-{m.group(2)}")
    return out


def extract_doc_ids(text: str):
    """返回去重后的政策标识集合，形如 {'〔2015〕119', '2023-7'}。"""
    ids = set()
    for m in DOC_BRACKET_RE.finditer(text):
        ids.add(f"〔{m.group(1)}〕{m.group(2)}")
    for m in DOC_ANNOUNCE_RE.finditer(text):
        ids.add(f"{m.group(1)}年第{m.group(2)}号")
    return sorted(ids)


def extract_m_codes(text: str):
    return sorted({m.group(0) for m in M_CODE_RE.finditer(text)})


def extract_e_codes(text: str):
    return sorted({m.group(0) for m in E_CODE_RE.finditer(text)})


def extract_status(text: str):
    """取最高等级（L3/L4 > L2 > L1 > L0）。"""
    found = STATUS_RE.findall(text[:2000])
    if not found:
        return None
    order = {"L4": 4, "L3": 3, "L2": 2, "L1": 1, "L0": 0}
    return max(found, key=lambda x: order.get(x, -1))


def extract_dates(text: str):
    out = set()
    for y, m, d in DATE_RE.findall(text):
        out.add(f"{y}-{int(m):02d}-{int(d):02d}")
    return sorted(out)[:6]
