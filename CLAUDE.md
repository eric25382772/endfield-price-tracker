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
- **武陵：** v2.0 起 1 行 7 格；item_id 13-19；顯示順序每天隨機，靠 OCR 名稱 + fuzzy match 對應
- **每日配額上限：** 谷地 +320 / 上限 960；武陵 +125 / 上限 250（4/17 改版前是 65/130）
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

## Release workflow

- **版本號規則：** 主版號（v2.x）= 遊戲內容改版；次版號 = 功能/修補
- 每版要在 [CHANGELOG.md](CHANGELOG.md) 加一行；[README.md](README.md) 開頭的「目前 GitHub 上架版本」也要更新
- setup.exe 用 Inno Setup 編譯，工具鏈與步驟看 [installer/README.md](installer/README.md)

## 鐵則（過去踩過的坑，不要違反）

### 好友列表 OCR 必須維持兩道過濾

動 [scanner.py](scanner.py) 的 `parse_friend_list` 時：

1. **價格 x 範圍：** `block['center_x'] < img_width * 0.75`（避開右邊百分比欄）
2. **單調遞減過濾：** 好友列表必為「販售價由高到低」，遇到反常變高的就視為雜訊跳過

**Why:** v2.0 實測時 OCR 把 `▲51.1%` 讀成 `5110`，只靠 x 範圍仍漏，必須兩道一起。

### 好友參考圖是固定資產

[data/item_images/friend/](data/item_images/friend/) 的 `item_*.png` 不可批次刪除、不可自動覆寫。F4 重置功能與 `save_friend_reference` 自動覆寫已在 v1.8 移除。新增物品時由開發者手動裁切放入。

**Why:** 自動覆寫一旦辨識錯就把錯圖存回，惡性循環越來越差（曾把 item_2.png 從 89KB 劣化到 11KB）。

### 圖片比對要同類型

好友畫面只能用 [data/item_images/friend/](data/item_images/friend/) 的同類型參考圖比對，不能拿市場小卡套。

**Why:** 比例 / 背景 / 角度差太大，ORB / HSV / 模板匹配全都跨類型不可靠。

### 開發機改 items seed 前先檢查 sqlite_sequence

本機 `items` 表 seq 可能因多次 reset 飆高。新增物品 seed 前先：

```sql
SELECT seq FROM sqlite_sequence WHERE name='items';  -- 對比 SELECT MAX(id) FROM items
-- 若 seq 遠大於 max(id)，先 UPDATE sqlite_sequence SET seq=<max_id>
```

**Why:** v2.0 加 item_18/19 時踩過，本機 seq=4409 導致新 item 拿到 4370/4371，破壞 image_matcher 的 `range(13, 20)` 硬編碼。一般使用者升級時不會踩到，只發生在開發機。

### F2 / F3 順序硬規則（v2.1 起）

F3 必須等 F2 至少成功跑過一次才會處理；F3 排隊或處理中時按 F2 會彈確認 modal。改 scanner 狀態機時不要拿掉這個保護。
