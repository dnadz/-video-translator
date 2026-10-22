@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "release\LocalVideoAI\LocalVideoAI.exe" (
    start "" "release\LocalVideoAI\LocalVideoAI.exe"
    exit /b
)
echo 尚未构建新版。请按 README.md 中的打包步骤生成程序。
pause
