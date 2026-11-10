@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 粤教职圈 · 一键更新网站

echo ========================================
echo   粤教职圈 · 一键更新网站
echo ========================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 没找到 python，请先安装 Python
    pause
    exit /b
)

echo [1/2] 重新生成职位数据...
python tools\parse_positions.py
if %errorlevel% neq 0 echo [警告] 解析步骤出错，继续尝试
python tools\ann_to_positions.py
python tools\normalize_final.py

echo.
echo [2/2] 推送到 GitHub...
python tools\push_github.py

echo.
echo ========================================
echo   完成！等 1-2 分钟后打开网站：
echo   https://dijia9960823.github.io/yuejiaozhipin66/
echo   按 Ctrl+Shift+R 强制刷新看最新数据
echo ========================================
pause
