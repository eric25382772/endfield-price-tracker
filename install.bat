@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================
echo  終末地彈性物資價格追蹤器 - 一鍵安裝
echo ========================================
echo.

echo [1/3] 檢查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [錯誤] 找不到 Python。
    echo.
    echo 請先安裝 Python 3.10 或更新版本：
    echo   https://www.python.org/downloads/
    echo.
    echo 安裝時務必勾選最下方的「Add Python to PATH」
    echo 裝完後重新開一個視窗，再雙擊本檔案。
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   偵測到 Python !PYVER!

for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    set PYMAJOR=%%a
    set PYMINOR=%%b
)
if !PYMAJOR! LSS 3 goto :pyver_old
if !PYMAJOR! EQU 3 if !PYMINOR! LSS 10 goto :pyver_old
goto :pyver_ok

:pyver_old
echo.
echo [錯誤] Python 版本過舊（需要 3.10 以上）。
echo 請到 https://www.python.org/downloads/ 下載新版。
echo.
pause
exit /b 1

:pyver_ok
echo.

echo [2/3] 安裝 Python 套件（首次約需 3-10 分鐘）...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [錯誤] 套件安裝失敗。請檢查網路連線後重新執行本檔案。
    echo.
    pause
    exit /b 1
)
echo.

echo [3/3] 預先下載 OCR 中文模型（約 300-500 MB，只需一次）...
echo   下載中，請耐心等待，畫面沒動不代表當機...
python -c "import easyocr; easyocr.Reader(['ch_tra','en'], gpu=False)"
if errorlevel 1 (
    echo.
    echo [警告] OCR 模型預先下載失敗，但不影響使用。
    echo 第一次按 F2 時會自動再下載一次。
    echo.
)
echo.

echo ========================================
echo  [OK] 安裝完成！
echo ========================================
echo.
echo 接下來：對 start_scanner.bat 點右鍵
echo         → 「以系統管理員身分執行」即可啟動。
echo.
pause
