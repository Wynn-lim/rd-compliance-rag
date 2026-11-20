"""公开前安全扫描：暂存区文件是否含敏感词。

词表从 scripts/sensitive_words.txt 读（该文件按设计不进版本库），
所以敏感词不出现在命令行、也不出现在任何入库文件里。

两种用法：
    git add -A && python -I scripts/scan_sensitive.py     # 扫暂存区
    python -I scripts/scan_sensitive.py --all             # 扫工作区全部入库文件

词表缺失时拒绝运行（fail closed）。
"""
import subprocess
import sys
from pathlib import Path

WORDS = Path(__file__).resolve().parent / "sensitive_words.txt"
words = [ln.strip() for ln in WORDS.read_text(encoding="utf-8").splitlines()
         if ln.strip() and not ln.strip().startswith("#")]
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

if "--all" in sys.argv:
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
else:
    files = subprocess.run(["git", "diff", "--cached", "--name-only"],
                           capture_output=True, text=True).stdout.split()
bad = {}
for f in files:
    try:
        t = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    hits = [w for w in words if w in t]
    if hits:
        bad[f] = hits

print("待提交文件数:", len(files))
if bad:
    print("检出敏感内容：")
    for k, v in bad.items():
        print("  ", k, v)
    raise SystemExit(1)
print("全仓敏感扫描通过")
print()
for f in sorted(files):
    print("  ", f)
