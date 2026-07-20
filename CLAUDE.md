# 終末地彈性物資價格追蹤器 — Claude Code 工作指引

明日方舟：終末地 (Arknights: Endfield) 的彈性物資市場價格追蹤工具。
使用者文件看 [README.md](README.md)，完整版本歷史看 [CHANGELOG.md](CHANGELOG.md)。

## Project at a glance (WHAT)

- **Tech：** Python 3.12 + Flask + EasyOCR + OpenCV + SQLite + Bootstrap 5
- **Entry：** `scanner.py`（按 F2/F3 觸發掃描，同時把 Flask 起在 127.0.0.1:5000）
- **核心模組：**
  - [scanner.py](scanner.py) — F2 自掃 / F3 好友掃，Queue + threading
  - [ocr/parser.py](ocr/parser.py) — OCR 文字解析（fuzzy match + x 座標配對）
  - [ocr/image_matcher.py](ocr/image_matcher.py) — 圖片比對（市場小卡 + 好友專用參考圖）
  - [data/repository.py](data/repository.py) — SQLite I/O；表：items, prices, friend_prices, stockpile, quotas
  - [data/item_images/](data/item_images/) 市場卡片；[data/item_images/friend/](data/item_images/friend/) 好友專用參考圖

## Game-specific facts (WHY，純 code 推不出來)

- **四號谷地：** 7+5 佈局（不是 6+6）；item_id 1-12
- **武陵：** v3.0 起 1 行 7 + 第 2 行 1 格；item_id 13-20（v2.0~v2.1.1 為 1 行 7 格，item_id 13-19）；顯示順序每天隨機，靠 OCR 名稱 + fuzzy match 對應
- **每日配額上限：** 谷地 +320 / 上限 960；武陵 +140 / 上限 280（v3.0 5/17 起；4/17~5/16 為 +125/250；4/17 前為 65/130）
- **好友畫面：** 一物一頁，左大圓框 + 右列表（# 名稱 + 4 位數價格）
- **好友物品圖裁切座標 (2560x1440)：** x=500-780, y=400-680
- **遊戲日期：** 以凌晨 4:00 為分界

## Development workflow (HOW)

- **Windows 環境：** python/pip 必透過 PowerShell 執行（不是 cmd / bash）
- **啟動 scanner.py：** 以管理員權限的 PowerShell `python scanner.py`
  - 需要管理員是因為 `keyboard` 套件監聽全域 F2/F3
  - Flask 會被自動拉起，瀏覽器自動開 `/compare`
- **不要強制 kill Python / PyTorch 進程**（會讓 GPU 當掉，重開機才能恢復）
- **建議流程：**
  - 改 OCR / scanner → 動 code 後請使用者按 F2/F3 實測
  - 改 UI → 直接看 http://127.0.0.1:5000/compare

## 細部規則放哪裡

過去踩過的坑已拆成 path-scoped rules，動到對應檔案時會自動載入：

| 檔案 | 涵蓋範圍 |
|---|---|
| [.claude/rules/ocr-scanner.md](.claude/rules/ocr-scanner.md) | `scanner.py` / `ocr/**` — 好友列表兩道過濾、同類型圖片比對、參考圖不可覆寫、F2/F3 順序 |
| [.claude/rules/item-assets.md](.claude/rules/item-assets.md) | `data/models.py` / `item_images/**` — 新增物品的圖要放兩處、sqlite_sequence 陷阱 |

發版流程是多步驟程序，走 skill：**`/release`**（版號規則 + 4 處同步 + push + 編 setup.exe + gh release）。
