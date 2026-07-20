---
paths:
  - "data/models.py"
  - "data/repository.py"
  - "data/item_images/**"
  - "static/images/items/**"
---

# 新增物品 / items seed 鐵則

## 市場圖要放「兩個地方」

新增 item 時，市場小卡 PNG 要同時複製到：

1. [data/item_images/](../../data/item_images/) — **辨識用**（image_matcher 讀這裡）
2. [static/images/items/](../../static/images/items/) — **compare 頁縮圖用**（`compare.html` 走 `/static/images/items/item_N.png`）

**Why:** 兩份是分開的路徑——歷史／預測頁走 `/item_image/<id>`（讀 data），compare 頁走 `/static/`（讀 static）。只放 data 會導致辨識正常但 /compare 縮圖破圖。v4.x 加 item_21、v5.0 加 item_22/23 都漏過 static 這份。好友參考圖 [data/item_images/friend/](../../data/item_images/friend/) 只有一份（掃描專用），不受此影響。

**兩份的裁切區域可以不同：** data 辨識版務必維持 image_matcher 的卡位區域（row1 y 420-660）才能跟 live 掃描同框比對；static 顯示版只求好看，若物品美術位置偏低（v5.0 的 item_22/23 美術落在 y≈470-710，用辨識框會被切一半），另裁一個框住整個物品的區域放 static 即可。

## 新增物品直接用顯式 id INSERT

```sql
INSERT OR IGNORE INTO items (id, name_cn, ...) VALUES (22, ...);
```

**Why（三次踩坑的結論）：**

- [data/models.py](../../data/models.py) 的 `init_db()` 用 `INSERT OR IGNORE`，SQLite AUTOINCREMENT **連被 IGNORE 的 row 也會消耗 seq**（每次啟動 +N，N=items 數）。
- v2.0 加 item_18/19：本機 seq=4409，新 item 拿到 4370/4371，破壞 image_matcher 的 `range(13, 20)` 硬編碼。
- v3.0 加 item_20：先重設 seq=19，使用者重啟 scanner 後 seq 被推到 79，item_20 拿到 id=39。
- v5.0 實測：**單純重設 seq 到 max_id 也救不回**——seed 迴圈先跑 N 個既有物品（每個 IGNORE 都推 +1），輪到新物品時 seq 早已越過 max_id。

顯式 id 之後重啟 seed 靠 name UNIQUE 略過，id 永遠對齊。這問題只發生在開發機，一般使用者升級不會踩到。

## 目前 id 配置

- 四號谷地：item_id 1-12（7+5 佈局）
- 武陵：item_id 13-20（v3.0 起 7+1）
