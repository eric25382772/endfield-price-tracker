---
name: release
description: 終末地追蹤器發版一條龍 — 改版號、更新 CHANGELOG、push、編 setup.exe、上傳 GitHub Release。使用者說「發版」「出新版」「升到 vX.Y」「打包」時使用。
---

# 發版流程

**一條龍做到底**：改版號 → push → 本機編 setup.exe → 上傳 release。不要 push 完就丟回給使用者。

## 0. 先確認版號該怎麼升

三碼版號規則：

| 位置 | 何時升 | 例 |
|---|---|---|
| 主版號 | **遊戲內容改版**（新區域、新物品、配額調整） | v4.x → v5.0 |
| 次版號 | 新功能 / 新流程 | v5.0 → v5.1 |
| 第三碼 | **修正 / 優化**——修既有功能、調語意邏輯、改門檻、補警告 | v5.0 → v5.0.1 |

**「修自己沒做對」不算升版：** 若上一版功能實作有誤，後續修正屬於該版完成，把改動合進**原 CHANGELOG 條目**，不要為了補做開新版號。

## 1. 同步改 4 個地方（少改任何一個都會脫節）

1. [CHANGELOG.md](../../../CHANGELOG.md) — 加一行
2. [README.md](../../../README.md) — **兩處**版號：
   - 開頭「目前 GitHub 上架版本」
   - 「版本更新紀錄」段的「最新版本」
   （v5.0 前只改開頭那處，導致下面那行從 v4.0 起長期脫節）
3. [installer/EndfieldTracker.iss](../../../installer/EndfieldTracker.iss) — `#define MyAppVersion`
   （決定 setup.exe 檔名 + 安裝程式顯示版本；v2.1.1/v3.0 都漏掉，到 v3.1 才補齊）
4. [installer/build.bat](../../../installer/build.bat) — 成功訊息裡的 `EndfieldTracker_Setup_vX.Y.exe` 檔名

改完用 grep 自我驗證，確認沒有殘留舊版號：

```powershell
Select-String -Path README.md,CHANGELOG.md,installer\EndfieldTracker.iss,installer\build.bat -Pattern 'v\d+\.\d+(\.\d+)?' | Select-Object -Last 20
```

## 2. Commit + push

```powershell
git add -A; if ($?) { git commit -m "vX.Y.Z：<一句話重點>" }; if ($?) { git push }
```

## 3. 本機編 setup.exe

用 Inno Setup 編譯（ISCC）。工具鏈與細節看 [installer/README.md](../../../installer/README.md)。

## 4. 上傳 GitHub Release

```powershell
gh release create vX.Y.Z installer\Output\EndfieldTracker_Setup_vX.Y.Z.exe --title "vX.Y.Z" --notes "<CHANGELOG 該版內容>"
```

Repo：`github.com/eric25382772/endfield-price-tracker`

## 驗證完成

- [ ] 4 個地方版號一致
- [ ] push 成功
- [ ] setup.exe 編出來且檔名版號正確
- [ ] release 頁面能下載到檔案
