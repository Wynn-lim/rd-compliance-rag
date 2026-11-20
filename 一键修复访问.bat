@echo off
chcp 65001 >nul
title 研发合规知识库 - 一键修复局域网访问
color 0A

echo.
echo ============================================
echo   研发合规知识库 · 一键修复局域网访问
echo ============================================
echo.
echo 本脚本会做四件事：
echo   1. 防火墙三配置的入站策略改为 BlockInbound
echo      （若原为 BlockInboundAlways，所有放行规则都会失效）
echo   2. 放行防火墙 TCP 8000 入站（三个网络类型都放）
echo   3. 把当前网络设为"专用"（公用网络限制更多）
echo   4. 确认服务在跑，不在则启动
echo.
echo 不改注册表，不加开机启动，不动其他任何设置。
echo.

REM ---- 检查管理员权限 ----
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo [!!] 需要管理员权限。
  echo.
  echo     请右键点本文件 -^> "以管理员身份运行"
  echo.
  pause
  exit /b 1
)

echo [1/4] 修正防火墙入站策略（域/专用/公用）...
netsh advfirewall set domainprofile   firewallpolicy BlockInbound,AllowOutbound >nul 2>&1
netsh advfirewall set privateprofile  firewallpolicy BlockInbound,AllowOutbound >nul 2>&1
netsh advfirewall set publicprofile   firewallpolicy BlockInbound,AllowOutbound >nul 2>&1
echo       完成
echo.

echo [2/4] 创建防火墙放行规则（TCP 8000）...
netsh advfirewall firewall delete rule name="研发合规知识库 8000" >nul 2>&1
netsh advfirewall firewall add rule name="研发合规知识库 8000" dir=in action=allow protocol=TCP localport=8000 profile=any enabled=yes description="内网研发合规知识库问答服务" >nul 2>&1
echo       完成
echo.

echo [3/4] 设置网络类型为"专用"...
powershell -NoProfile -Command "Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Private" 2>nul
echo       完成
echo.

echo [4/4] 检查服务是否在运行...
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
  echo       正在监听 OK
) else (
  echo       没有在监听！正在为你启动...
  start "" "%~dp0启动_局域网.bat"
  timeout /t 12 /nobreak >nul
  echo       已启动
)
echo.

REM ---- 取内网 IP ----
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /c:"IPv4" ^| findstr "192.168"') do (
  for /f "tokens=1" %%a in ("%%i") do set IP=%%a
)

echo ============================================
echo   修复完成！
echo.
echo   同事电脑 / 手机 现在访问这个地址：
echo.
echo        http://%IP%:8000
echo.
echo   账号：zhishi
echo   密码：kb2026
echo.
echo   注意：地址开头是 http:// 不是 https://
echo        :8000 不能漏，别在微信里点开
echo ============================================
echo.
echo 正在验证端口可达性...
powershell -NoProfile -Command "if (Test-NetConnection -ComputerName %IP% -Port 8000 -InformationLevel Quiet) { '   结果：端口 8000 可达 OK' } else { '   结果：仍不通，换台设备试试，或看下方排障' }"
echo.
pause
