---
paths:
  - "scanner.py"
  - "ocr/**/*.py"
---

# 掃描器 / OCR 鐵則（過去踩過的坑，不要違反）

## 好友列表 OCR 必須維持兩道過濾

動 [scanner.py](../../scanner.py) 的 `parse_friend_list` 時：

1. **價格 x 範圍：** `block['center_x'] < img_width * 0.75`（避開右邊百分比欄）
2. **單調遞減過濾：** 好友列表必為「販售價由高到低」，遇到反常變高的就視為雜訊跳過

**Why:** v2.0 實測時 OCR 把 `▲51.1%` 讀成 `5110`，只靠 x 範圍仍漏，必須兩道一起。

## 圖片比對要同類型

好友畫面只能用 [data/item_images/friend/](../../data/item_images/friend/) 的同類型參考圖比對，不能拿市場小卡套。

**Why:** 比例 / 背景 / 角度差太大，ORB / HSV / 模板匹配全都跨類型不可靠。

## 好友參考圖是固定資產

[data/item_images/friend/](../../data/item_images/friend/) 的 `item_*.png` 不可批次刪除、不可自動覆寫。F4 重置功能與 `save_friend_reference` 自動覆寫已在 v1.8 移除。新增物品時由開發者手動裁切放入。

**Why:** 自動覆寫一旦辨識錯就把錯圖存回，惡性循環越來越差（曾把 item_2.png 從 89KB 劣化到 11KB）。

## F2 / F3 順序硬規則（v2.1 起）

F3 必須等 F2 至少成功跑過一次才會處理；F3 排隊或處理中時按 F2 會彈確認 modal。改 scanner 狀態機時不要拿掉這個保護。

## 實測方式

改完 OCR / scanner 後請使用者按 F2/F3 實測，不要只靠靜態檢查宣告完成。
