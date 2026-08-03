# 終末地 彈性物資價格追蹤器

> 目前 GitHub 上架版本：**v5.1.2**

明日方舟：終末地 (Arknights: Endfield) 的彈性物資市場價格追蹤工具。
自動辨識遊戲畫面中的物品與價格，比對好友市場找出最佳利潤。

## 功能

- **F2 掃描自己的市場** — OCR 自動辨識物品名稱與價格，偵測區域（四號谷地 / 武陵）
- **F3 掃描好友價格** — 連續截圖、佇列處理，逐一辨識好友價格列表
- **F4 記錄目前持有** — 在物資調度畫面辨識「目前持有」並記錄囤貨
- **利潤比對** — 網頁顯示自己價格 vs 好友最高價，計算利潤並給出買入建議
- **區域鎖定** — F2 掃完自動鎖定區域，F3 只在該區域內比對物品
- **自動更新** — 每次啟動自動檢查並更新到最新版（只抓程式碼、數秒完成），不必再回這裡重新下載安裝程式；網頁導覽列可看到目前版本與更新紀錄

## 系統需求

- Windows 10 / 11
- 遊戲解析度建議 2560x1440（最低 1920x1080）
- 首次啟動需網路下載 OCR 模型

## 安裝

1. 到 [Releases](https://github.com/eric25382772/endfield-price-tracker/releases) 下載 `EndfieldTracker_Setup_vX.XX.exe`
<img width="1451" height="968" alt="image" src="https://github.com/user-attachments/assets/5dd9cee8-601f-4427-87b4-7e10ea271978" />
<img width="1247" height="602" alt="image" src="https://github.com/user-attachments/assets/6cc2c064-e716-490d-b032-8822505c5385" />

2. 雙擊執行
<img width="1136" height="628" alt="image" src="https://github.com/user-attachments/assets/9527fece-1f71-44be-be79-c864bb08fcdd" />

若 Windows SmartScreen 跳警告，點「其他資訊 → 仍要執行」。

<img width="541" height="500" alt="image" src="https://github.com/user-attachments/assets/f0a7e39f-86d4-401b-972e-65a6cd887d6c" />
<img width="578" height="515" alt="image" src="https://github.com/user-attachments/assets/be63cbcb-98c1-4524-9267-dc2e9c48b9e0" />

  一路「下一步」到完成
  
<img width="638" height="493" alt="image" src="https://github.com/user-attachments/assets/acb9179e-1353-4f63-8876-fbdd1f31f9a8" />
<img width="646" height="498" alt="image" src="https://github.com/user-attachments/assets/11e53550-e7b3-4f6c-995d-ef14f42265cb" />
<img width="650" height="494" alt="image" src="https://github.com/user-attachments/assets/154156fd-5e90-40bd-bb1c-5feb94d14228" />
<img width="648" height="504" alt="image" src="https://github.com/user-attachments/assets/df0d46c5-f85d-4d1d-ae90-00bf19200fbe" />

3. 完成後雙擊桌面的「終末地追蹤器」捷徑啟動（會自動請求管理員權限）

<img width="2560" height="1440" alt="image" src="https://github.com/user-attachments/assets/d9a233ec-4fd1-40da-af13-f8191d7edf12" />
<img width="510" height="381" alt="image" src="https://github.com/user-attachments/assets/827bc291-3dc2-4c4e-acd7-488274e482b4" />

4.看到正在開啟網頁表示安裝成功啟動中(首次開啟會較慢 要載入OCR模型)

<img width="400" height="170" alt="image" src="https://github.com/user-attachments/assets/fd529faf-ab45-4a8d-8049-aaf67ba889d1" />



## 使用方式

### 快捷鍵

| 按鍵 | 功能 |
|------|------|
| **F2** | 掃描自己的市場價格 |
| **F3** | 掃描好友的市場價格 |
| **F4** | 記錄目前持有（囤貨） |
| **Ctrl+Shift+Q** | 結束掃描器 |

### 操作流程

1. 雙擊桌面上的終末地追蹤器，打開網頁
<img width="294" height="458" alt="image" src="https://github.com/user-attachments/assets/d73382fa-92a5-4829-836d-0e0979a97156" />
<img width="2560" height="1440" alt="image" src="https://github.com/user-attachments/assets/76b4598f-9a1e-446a-99d1-3ea4eff0ded5" />
<img width="400" height="170" alt="image" src="https://github.com/user-attachments/assets/fd529faf-ab45-4a8d-8049-aaf67ba889d1" />
<img width="2560" height="1440" alt="image" src="https://github.com/user-attachments/assets/3efeaf5d-d3b3-4883-b12a-36fd9028415b" />

2.到自己的彈性需求物資畫面，按F2，系統會自動辨識物品名稱、價格，並帶到辨識地區的表格畫面
<img width="2560" height="1440" alt="image" src="https://github.com/user-attachments/assets/f4e29aa0-ebfd-48ba-bfcc-e8277c5b76d4" />
<img width="2560" height="1271" alt="image" src="https://github.com/user-attachments/assets/7469e596-2a08-4c62-be0d-8add4109231e" />
3.點擊各物資好友價格，按F3，系統會自動辨識，並計算出利潤
(F2 F3辨識途中可繼續使用F3對下一個物資進行截圖，系統會先儲存截圖並依序辨識出來不需等待前一張辨識完成)
<img width="1865" height="985" alt="image" src="https://github.com/user-attachments/assets/1e3365f6-d7e8-425c-ad75-a204179eadac" />
<img width="1312" height="1139" alt="image" src="https://github.com/user-attachments/assets/177acb3e-80b5-4a5b-a4ee-21e985250a2a" />
<img width="1291" height="1140" alt="image" src="https://github.com/user-attachments/assets/e3911f87-c316-469e-b7c2-38daca1894ef" />

重要：**一定要先按 F2 掃描自己市場**，系統才知道在哪個地區，F3 才能正確辨識貨物。

## 版本更新紀錄

詳見 [CHANGELOG.md](CHANGELOG.md)。最新版本：**v5.1.2**。

## 注意事項

- **首次啟動較慢**：OCR 引擎首次載入需要下載語言模型，之後會快取在本機
- **只支援 Windows**：掃描器使用 Win32 API 擷取遊戲視窗
- **需要管理員權限**：監聽全域快捷鍵 F2 / F3 / F4 需要管理員權限
- **先開追蹤器再開遊戲**：避免 UAC 提示干擾遊戲
- **遊戲要在前景**：按 F2 / F3 / F4 時，遊戲視窗必須在最前面，否則會截到其他畫面
- **每日重置時間**：遊戲日期以凌晨 4:00 為分界，4:00 前的操作算前一天
