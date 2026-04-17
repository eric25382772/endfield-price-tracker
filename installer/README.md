# Inno Setup 安裝精靈建置說明

此資料夾用來打包 `EndfieldTracker_Setup.exe`（v1.11+ 提供給一般使用者的安裝包）。

## 一次性環境準備

1. **安裝 Inno Setup 6**：https://jrsoftware.org/isdl.php → 下載 `innosetup-6.x.exe` 安裝
2. **下載 InnoDownloadPlugin (idp)**：https://mitrich.net/blog/inno-download-plugin/
   - 解壓後把 `InnoDownloadPlugin\` 整個資料夾複製到本資料夾（與 `EndfieldTracker.iss` 同層）
   - 確認路徑：`installer/InnoDownloadPlugin/idp.iss` 存在

## 建置

雙擊 `build.bat`，編譯產出會放在 `dist/EndfieldTracker_Setup_v1.11.exe`（不進 git，掛到 GitHub Release）。

## 為什麼需要 idp

Inno Setup 本身無法在安裝過程中下載檔案；idp 提供 `idpAddFile` 函式讓我們在沒偵測到 Python 時，從官方 ftp 下載 Python 安裝程式並靜默執行。
