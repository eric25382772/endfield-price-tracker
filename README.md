<div align="center">

# 終末地 彈性物資價格追蹤器

**明日方舟：終末地 (Arknights: Endfield) 彈性物資市場價格追蹤工具**

自動辨識遊戲畫面中的物品與價格，比對好友市場，一眼找出最賺的交易。

[![release](https://img.shields.io/github/v/release/eric25382772/endfield-price-tracker?style=for-the-badge&color=2ea043)](https://github.com/eric25382772/endfield-price-tracker/releases/latest)
[![downloads](https://img.shields.io/github/downloads/eric25382772/endfield-price-tracker/total?style=for-the-badge&color=1f6feb)](https://github.com/eric25382772/endfield-price-tracker/releases)
[![platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-0078d4?style=for-the-badge)](#系統需求)
[![python](https://img.shields.io/badge/python-3.12-3776ab?style=for-the-badge)](#系統需求)

**[⬇ 立即下載](https://github.com/eric25382772/endfield-price-tracker/releases/latest)** ·
[安裝步驟](#安裝步驟) ·
[使用方式](#使用方式) ·
[更新紀錄](CHANGELOG.md)

</div>

---

## 目錄

- [功能特色](#功能特色)
- [系統需求](#系統需求)
- [安裝步驟](#安裝步驟)
- [使用方式](#使用方式)
- [注意事項](#注意事項)
- [版本更新紀錄](#版本更新紀錄)

---

## 功能特色

| 功能 | 說明 |
| :--- | :--- |
| **F2 掃描自己的市場** | OCR 自動辨識物品名稱與價格，並偵測目前區域（四號谷地 / 武陵） |
| **F3 掃描好友價格** | 可連續截圖、佇列處理，逐一辨識好友價格列表 |
| **F4 記錄目前持有** | 在物資調度畫面辨識「目前持有」並記錄囤貨 |
| **利潤比對** | 網頁顯示自己價格 vs 好友最高價，計算利潤並給出買入建議 |
| **區域鎖定** | F2 掃完自動鎖定區域，F3 只在該區域內比對物品 |
| **自動更新** | 每次啟動自動檢查並更新到最新版（只抓程式碼、數秒完成），不必再回這裡重新下載安裝程式；網頁導覽列可看到目前版本與更新紀錄 |

---

## 系統需求

| 項目 | 需求 |
| :--- | :--- |
| 作業系統 | Windows 10 / 11 |
| 遊戲解析度 | 建議 2560 x 1440（最低 1920 x 1080） |
| 網路 | 首次啟動需連線下載 OCR 模型 |
| 權限 | 需要管理員權限（監聽全域快捷鍵） |

---

## 安裝步驟

### 步驟 1 — 下載安裝程式

前往 **[Releases](https://github.com/eric25382772/endfield-price-tracker/releases)** 頁面，下載最新版的 `EndfieldTracker_Setup_vX.XX.exe`。

<p align="center">
  <img src="https://github.com/user-attachments/assets/5dd9cee8-601f-4427-87b4-7e10ea271978" width="820" alt="Releases 頁面"><br>
  <sub>① 開啟 Releases 頁面，找到最新版本</sub>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/6cc2c064-e716-490d-b032-8822505c5385" width="820" alt="下載安裝檔"><br>
  <sub>② 點擊 <code>EndfieldTracker_Setup_vX.XX.exe</code> 下載</sub>
</p>

### 步驟 2 — 執行安裝程式

下載完成後雙擊執行。

<p align="center">
  <img src="https://github.com/user-attachments/assets/9527fece-1f71-44be-be79-c864bb08fcdd" width="760" alt="雙擊安裝檔"><br>
  <sub>雙擊下載好的安裝檔</sub>
</p>

> [!NOTE]
> 若 Windows SmartScreen 跳出警告，點 **「其他資訊」→「仍要執行」** 即可。
> 這是因為安裝程式沒有付費簽章，不是病毒。

<table>
<tr>
<td width="50%" align="center"><img src="https://github.com/user-attachments/assets/f0a7e39f-86d4-401b-972e-65a6cd887d6c" width="100%" alt="SmartScreen 警告"><br><sub>① 點「其他資訊」</sub></td>
<td width="50%" align="center"><img src="https://github.com/user-attachments/assets/be63cbcb-98c1-4524-9267-dc2e9c48b9e0" width="100%" alt="仍要執行"><br><sub>② 點「仍要執行」</sub></td>
</tr>
</table>

### 步驟 3 — 一路「下一步」到完成

安裝精靈全部使用預設值即可，直接按到底。

<table>
<tr>
<td width="50%" align="center"><img src="https://github.com/user-attachments/assets/acb9179e-1353-4f63-8876-fbdd1f31f9a8" width="100%" alt="安裝精靈 1"><br><sub>①</sub></td>
<td width="50%" align="center"><img src="https://github.com/user-attachments/assets/11e53550-e7b3-4f6c-995d-ef14f42265cb" width="100%" alt="安裝精靈 2"><br><sub>②</sub></td>
</tr>
<tr>
<td width="50%" align="center"><img src="https://github.com/user-attachments/assets/154156fd-5e90-40bd-bb1c-5feb94d14228" width="100%" alt="安裝精靈 3"><br><sub>③</sub></td>
<td width="50%" align="center"><img src="https://github.com/user-attachments/assets/df0d46c5-f85d-4d1d-ae90-00bf19200fbe" width="100%" alt="安裝精靈 4"><br><sub>④ 完成</sub></td>
</tr>
</table>

### 步驟 4 — 啟動追蹤器

雙擊桌面的 **「終末地追蹤器」** 捷徑，程式會自動請求管理員權限。

<p align="center">
  <img src="https://github.com/user-attachments/assets/d9a233ec-4fd1-40da-af13-f8191d7edf12" width="820" alt="桌面捷徑"><br>
  <sub>① 雙擊桌面捷徑</sub>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/827bc291-3dc2-4c4e-acd7-488274e482b4" width="440" alt="UAC 權限提示"><br>
  <sub>② 出現權限提示時按「是」</sub>
</p>

### 步驟 5 — 確認安裝成功

看到「正在開啟網頁」的視窗，就代表安裝成功、程式啟動中。

<p align="center">
  <img src="https://github.com/user-attachments/assets/fd529faf-ab45-4a8d-8049-aaf67ba889d1" width="400" alt="正在開啟網頁"><br>
  <sub>看到這個視窗就成功了</sub>
</p>

> [!TIP]
> **首次開啟會比較慢**，因為要載入 OCR 模型，請耐心等候；之後啟動就快了。

---

## 使用方式

### 快捷鍵

| 按鍵 | 功能 | 使用時機 |
| :---: | :--- | :--- |
| **F2** | 掃描自己的市場價格 | 在自己的彈性需求物資畫面 |
| **F3** | 掃描好友的市場價格 | 點開某物資的好友價格畫面 |
| **F4** | 記錄目前持有（囤貨） | 在物資調度畫面 |
| **Ctrl + Shift + Q** | 結束掃描器 | 收工時 |

### 操作流程

> [!IMPORTANT]
> **一定要先按 F2 掃描自己的市場**，系統才知道你在哪個地區，F3 才能正確辨識貨物。

#### 步驟 1 — 開啟追蹤器

雙擊桌面上的「終末地追蹤器」，等它自動打開網頁。

<table>
<tr>
<td width="30%" align="center"><img src="https://github.com/user-attachments/assets/d73382fa-92a5-4829-836d-0e0979a97156" width="100%" alt="桌面捷徑"><br><sub>① 雙擊桌面捷徑</sub></td>
<td width="70%" align="center"><img src="https://github.com/user-attachments/assets/76b4598f-9a1e-446a-99d1-3ea4eff0ded5" width="100%" alt="啟動中"><br><sub>② 程式啟動中</sub></td>
</tr>
</table>

<p align="center">
  <img src="https://github.com/user-attachments/assets/fd529faf-ab45-4a8d-8049-aaf67ba889d1" width="400" alt="正在開啟網頁"><br>
  <sub>③ 出現「正在開啟網頁」</sub>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/3efeaf5d-d3b3-4883-b12a-36fd9028415b" width="820" alt="比對網頁"><br>
  <sub>④ 瀏覽器自動開啟比對頁面</sub>
</p>

#### 步驟 2 — 按 F2 掃描自己的市場

進入自己的**彈性需求物資**畫面，按 **F2**。系統會自動辨識物品名稱與價格，並帶到對應地區的表格畫面。

<p align="center">
  <img src="https://github.com/user-attachments/assets/f4e29aa0-ebfd-48ba-bfcc-e8277c5b76d4" width="820" alt="彈性需求物資畫面"><br>
  <sub>① 在此畫面按 F2</sub>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/7469e596-2a08-4c62-be0d-8add4109231e" width="820" alt="辨識結果表格"><br>
  <sub>② 網頁自動帶出該地區的表格</sub>
</p>

#### 步驟 3 — 按 F3 掃描好友價格

點擊各物資的**好友價格**畫面，按 **F3**。系統會自動辨識並計算出利潤。

> [!TIP]
> **不用等辨識跑完**。F2 還在辨識地區時就可以先按 F3 截圖，F3 辨識途中也可以繼續按 F3 對下一個物資截圖。
> 系統會先把截圖存下來排隊，再依序辨識，不必等前一張跑完。

<p align="center">
  <img src="https://github.com/user-attachments/assets/1e3365f6-d7e8-425c-ad75-a204179eadac" width="820" alt="好友價格畫面"><br>
  <sub>① 在好友價格畫面按 F3</sub>
</p>

<table>
<tr>
<td width="50%" align="center"><img src="https://github.com/user-attachments/assets/177acb3e-80b5-4a5b-a4ee-21e985250a2a" width="100%" alt="辨識中"><br><sub>② 辨識中（可繼續按 F3 掃下一個）</sub></td>
<td width="50%" align="center"><img src="https://github.com/user-attachments/assets/e3911f87-c316-469e-b7c2-38daca1894ef" width="100%" alt="辨識完成"><br><sub>③ 辨識完成，自動算出利潤</sub></td>
</tr>
</table>

#### 步驟 4 — 按 F4 記錄囤貨

跟 F2 是**同一個畫面**：物資調度 →「彈性需求物資」分頁，上半部的**「目前持有」**區就是你囤的貨。在這裡按 **F4**，系統會辨識持有的物資與買入價並記錄下來。

<p align="center">
  <img src="docs/images/f4_game_stockpile.png" width="820" alt="目前持有區"><br>
  <sub>① 在「目前持有」區按 F4</sub>
</p>

回網頁重新整理，最下方的**「囤貨持有」**區就會列出持有清單，包含買入價、好友最高價、囤貨利潤與建議賣出日。實際賣掉後按「賣出」把該筆結掉。

<p align="center">
  <img src="docs/images/f4_web_stockpile.png" width="820" alt="囤貨持有區"><br>
  <sub>② 網頁最下方出現「囤貨持有」紀錄</sub>
</p>

> [!NOTE]
> F4 跟 F2 / F3 各自獨立，**不必先按 F2** 也能用，隨時想記錄就按。
> 同一天、同一個物品只會記一筆，重複按不會重複計算。

> [!WARNING]
> 若出現 **「未辨識到『目前持有』」**，代表畫面沒有停在物資調度頁，或是截到了其他視窗。
> 請確認遊戲在最前面、畫面停在物資調度頁，再按一次 F4。

---

## 注意事項

> [!WARNING]
> 按 F2 / F3 / F4 時，**遊戲視窗必須在最前面**，否則會截到其他畫面。

| 項目 | 說明 |
| :--- | :--- |
| **首次啟動較慢** | OCR 引擎首次載入需要下載語言模型，之後會快取在本機 |
| **只支援 Windows** | 掃描器使用 Win32 API 擷取遊戲視窗 |
| **需要管理員權限** | 監聽全域快捷鍵 F2 / F3 / F4 需要管理員權限 |
| **先開追蹤器再開遊戲** | 避免 UAC 提示干擾遊戲 |
| **遊戲要在前景** | 按 F2 / F3 / F4 時，遊戲視窗必須在最前面 |
| **每日重置時間** | 遊戲日期以凌晨 4:00 為分界，4:00 前的操作算前一天 |

---

## 版本更新紀錄

目前 GitHub 上架版本：**v5.1.4**

完整版本歷史詳見 **[CHANGELOG.md](CHANGELOG.md)**。

<div align="center">
<sub>如果這個工具幫到你，歡迎給一顆 ⭐</sub>
</div>
