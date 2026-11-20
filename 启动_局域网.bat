@echo off
chcp 65001 >nul
cd /d %~dp0

echo ============================================
echo   研发合规知识库 - 局域网启动
echo ============================================
echo.

set RAG_DENSE_MODEL=BAAI/bge-small-zh-v1.5
set RAG_RERANK_MODEL=__disabled__
set PYTHONUTF8=1

echo 正在启动（首次加载模型约需 10 秒）...
echo.
echo 本机访问：  http://127.0.0.1:8000
echo.
echo 同一 WiFi 内，把下面地址发给别人：
echo.
python -I web\server.py --host 0.0.0.0 --port 8000

echo.
echo 服务已停止。按任意键关闭窗口。
pause >nul
