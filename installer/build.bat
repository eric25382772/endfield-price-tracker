@echo off
chcp 65001 >nul
setlocal

set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo [錯誤] 找不到 Inno Setup 6 編譯器。
    echo.
    echo 請先安裝 Inno Setup 6：https://jrsoftware.org/isdl.php
    echo 並安裝 InnoDownloadPlugin：https://mitrich.net/blog/inno-download-plugin/
    echo （把 idp 解壓到 %~dp0InnoDownloadPlugin\）
    pause
    exit /b 1
)

if not exist "%~dp0InnoDownloadPlugin\idp.iss" (
    echo [錯誤] 找不到 InnoDownloadPlugin：
    echo   %~dp0InnoDownloadPlugin\idp.iss
    echo.
    echo 請從 https://mitrich.net/blog/inno-download-plugin/ 下載
    echo 並把整個 InnoDownloadPlugin 資料夾複製到 %~dp0
    pause
    exit /b 1
)

%ISCC% "%~dp0EndfieldTracker.iss"
if errorlevel 1 (
    echo.
    echo [錯誤] 編譯失敗。
    pause
    exit /b 1
)

echo.
echo ========================================
echo  [OK] 安裝精靈已產出：
echo  %~dp0..\dist\EndfieldTracker_Setup_v1.11.exe
echo ========================================
pause
