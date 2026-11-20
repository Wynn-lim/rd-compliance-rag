@echo off
chcp 65001 >nul
title 研发合规知识库 - 访问地址（复制这个）
color 0E

echo.
echo ============================================
echo.
echo    同事电脑 / 手机，请访问这个地址：
echo.
echo        http://192.168.1.166:8000
echo.
echo    注意：
echo      - 开头是 http://  不是 https://
echo      - 后面的 :8000 不能漏
echo      - 别在微信里点开，用 Edge 或 Chrome
echo.
echo    账号：zhishi
echo    密码：kb2026
echo.
echo    （IP 变了就改 启动_局域网.bat 旁边
echo      这个文件里的地址，或重跑一键修复访问.bat）
echo.
echo ============================================
echo.
echo | set /p="http://192.168.1.166:8000" <nul | clip
echo 地址已复制到剪贴板，直接粘贴到浏览器。
echo.
pause
