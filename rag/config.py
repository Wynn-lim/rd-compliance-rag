"""路径、分层定义与检索参数。"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KB_ROOT = PROJECT_ROOT / "kb_src" / "01_知识库全量"
KB_PACKAGE = PROJECT_ROOT / "kb_src"
DATA_DIR = PROJECT_ROOT / "data"
WEB_DIR = PROJECT_ROOT / "web"

TONG_GANG = KB_ROOT / "00_总纲"

# ---- 四层 + 治理层定义（施工规格 §2.2 / §3.3）----
GOVERNANCE_FILES = {
    "route": [TONG_GANG / "03_条目索引.md"],
    "ledger": [TONG_GANG / "01_政策文件总台账.md"],
    "errata": [TONG_GANG / "02_勘误记录.md"],
    "method": [
        TONG_GANG / "00_知识库总纲.md",
        TONG_GANG / "05_知识库使用提示词.md",
        TONG_GANG / "06_知识库Agent构建步骤提示词.md",
    ],
    "log": [TONG_GANG / "04_更新日志.md"],
}

# 知识层：01~12 模块下所有 M*.md；99_收件箱 排除（非知识资产）
KNOWLEDGE_DIRS = [
    "01_政策法规库", "02_研发组织与人才", "03_研发管理制度", "04_研发活动认定",
    "05_研发全流程", "06_费用归集核算", "07_申报口径", "08_证据链与备查",
    "09_研发效能指标", "10_稽查与自查", "11_行业专题", "12_案例库",
]
EXCLUDED_DIRS = {"99_收件箱", "13_内容产品化"}

LAYER_LABEL = {
    "route": "路由层（条目索引）",
    "ledger": "台账层（政策时效）",
    "errata": "纠错层（勘误/铁律/检查项）",
    "method": "治理层（方法论/提示词）",
    "knowledge": "知识层（M 条目正文）",
    "log": "时间线（更新日志）",
}

# ---- 分块参数 ----
MAX_CHUNK_CHARS = 1100        # 规格：每块 ≤1000 字，留 10% 余量
MIN_CHUNK_CHARS = 60
TABLE_KEEP_TOGETHER = True

# ---- 检索参数（初值，评测后定标）----
BM25_TOP_K = 60
DENSE_TOP_K = 60
FUSED_TOP_K = 40
FINAL_TOP_K = 8
RRF_K = 60
RERANK_CANDIDATES = 24         # 只对融合后前 N 条做交叉编码（CPU 上控延迟）
LAYER_ROUTE_TOP_K = 6          # 路由层单独召回后用于给知识层加权

# 纠错层（勘误）作为附加校验单独召回，不进主结果名额
ERRATA_TOP_K = 20              # 纠错层候选召回数
ERRATA_TOP_N = 5               # 最多返回几条纠错提示（实测 3 条会漏掉排第 4 的 E-005）
ERRATA_MIN_SIM = 0.40          # 纠错层向量相似度下限

DENSE_MODEL = os.environ.get("RAG_DENSE_MODEL", "BAAI/bge-m3")
RERANK_MODEL = os.environ.get("RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
