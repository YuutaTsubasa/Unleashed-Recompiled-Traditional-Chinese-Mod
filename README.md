# Unleashed Recompiled 繁體中文化 MOD

[Unleashed Recompiled](https://github.com/hedge-dev/UnleashedRecomp)（Sonic Unleashed 的 PC 移植版）非官方繁體中文化 MOD。

- 遊戲內文字：選單、村民對話、提示、道具說明、關卡與任務、媒體室、DLC 世界地圖
- 過場字幕：依**日語配音**的時間軸翻譯
- 介面圖片：標題選單、關卡／國家名稱、暫停選單、讀取畫面操作說明、對話名牌等
- 字型：[Noto Sans TC](https://fonts.google.com/noto/specimen/Noto+Sans+TC)

MOD 取代的是**日文語言槽**：遊戲語言設為「日文」即顯示繁體中文，語音可自由選擇日語或英語。

> 本 repo **不含任何遊戲資料**。MOD 需要用你自己的遊戲檔在本機產生。

## 產生 MOD

需求：Windows、[Python 3.10+](https://www.python.org/)、已安裝好的 Unleashed Recompiled（含 `game/` 資料夾，DLC 可選）、Noto Sans TC 字型。

```bash
pip install -r requirements.txt
```

```bash
python build_mod.py --game "D:\Games\UnleashedRecompiled" --zip
```

- `--game`：Unleashed Recompiled 的安裝資料夾（有 `game/`、`dlc/`、`UnleashedRecomp.exe` 的那層）
- 產出：`dist/UnleashedTC/`（加上 `--zip` 會另外產生 `dist/UnleashedTC.zip`）
- 字型預設為 `C:\Windows\Fonts\NotoSansTC-VF.ttf`；若系統沒有，可從 Google Fonts 下載 Noto Sans TC，再用 `--font <路徑>` 指定（建議使用可變字型 `NotoSansTC-VariableFont_wght.ttf`）

整個過程約一分鐘。

## 安裝

1. 用 [Hedge Mod Manager](https://github.com/hedge-dev/HedgeModManager) 安裝：把 `dist/UnleashedTC` 資料夾（或 zip）加入 Unleashed Recompiled 的 MOD 清單並勾選
2. 遊戲內「選項 → 語言」設為日文

## 已知限制

- Unleashed Recompiled 本身的設定選單與安裝器（寫在 `UnleashedRecomp.exe` 內）仍為原文
- 原版部分文字的彩色強調與日文注音假名在中文版中移除
- MOD 採用 Hedge Mod Manager 的附加封存檔格式（`+名稱.ar` / `+名稱.arl`），只附加修改過的檔案，不替換原始封存檔

## 專案結構

| 路徑 | 說明 |
| --- | --- |
| `data/zh_text.json` | 譯文：`封存檔 → 文字表(.fco) → "群組/格名#序號" → 中文` |
| `data/glossary.md` | 譯名表（角色、地名、關卡、道具） |
| `tclib/images.py` | 介面圖片文字的位置與譯文 |
| `tclib/converse.py` | 重建文字表（FCO）、字型表（FTE）與字型貼圖 |
| `tclib/archive.py` | AR / ARL 封存檔讀寫 |
| `tools/xdec/` | Xbox 360 XCompress（LZX）解壓工具（原始碼與預先編譯的 `xdec.exe`） |
| `build_mod.py` | 產生 MOD 的主程式 |

譯文中的特殊標記：`{c0}` 換行、`{iN}` 按鈕圖示、`{cN}` / `{?N}` 其他控制碼，修改譯文時請保留。

## 授權

- 本專案程式碼與譯文：[MIT License](LICENSE)
- 第三方元件見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)

本專案為非官方愛好者作品，與 SEGA 無關。Sonic the Hedgehog 及相關名稱、角色為 SEGA 的商標及著作。
