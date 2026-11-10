@echo off
chcp 65001 >nul
cd /d F:\XIANG\粤教师\粤教职圈

echo ========================================
echo  粤教职圈 · 一键推 GitHub
echo ========================================
echo.

REM 检查 git 是否安装
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 没装 Git！请先去 https://git-scm.com/download/win 下载安装
    echo 安装完重启电脑再双击这个脚本
    pause
    exit /b
)

REM 检查目录是否已是 git 仓库
if not exist .git (
    echo 初始化 git 仓库...
    git init
)

echo 添加所有文件...
git add -A

if %errorlevel% neq 0 (
    echo ❌ git add 失败
    pause
    exit /b
)

git commit -m "初始版本：粤教职圈 + 自动更新管线" 2>nul

REM 确认远程仓库
git remote -v | findstr "origin" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo 请输入你的 GitHub 仓库地址（按回车跳过使用默认 yuejiaozhipin66）：
    set /p REPO_URL=
    if "%REPO_URL%"=="" set REPO_URL=https://github.com/DIjia9960823/yuejiaozhipin66.git
    git remote add origin %REPO_URL%
    echo 已设置远程：%REPO_URL%
)

echo.
echo 推送到 GitHub...
git branch -M main 2>nul
git push -u origin main --force

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo  ✅ 推送成功！
    echo  现在去仓库页面点 Actions 标签 → 手动点 Run workflow 测试
    echo ========================================
) else (
    echo.
    echo ❌ 推送失败，可能需要先在 GitHub 上新建仓库
    echo 去 https://github.com/new 创建一个空仓库（名字随便，比如 yuejiaozhipin66）
    echo 创建完再双击这个脚本
)
pause
