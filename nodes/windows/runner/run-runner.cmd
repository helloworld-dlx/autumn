@echo off
setlocal
cd /d D:\JarvisWorkspace\JarvisRunner
"%LOCALAPPDATA%\Programs\Python\Python313\python.exe" -m jarvis_runner.cli serve-tailscale > "%TEMP%\jarvis-runner-console.log" 2>&1
exit /b %ERRORLEVEL%
