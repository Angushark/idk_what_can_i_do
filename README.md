# 論文翻譯 Paper Translate

上傳英文論文 PDF，就能下載**版面完全相同**的繁體中文版本：
頁數、圖片、向量圖表、表格框線都留在原位，只把文字換成中文。

## 安裝

需要 Python 3.10 以上。

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 使用方式

### 網頁介面（上傳 → 下載）

```bash
python -m paper_translate.web
```

接著用瀏覽器打開 <http://127.0.0.1:5000>，把 PDF 拖進去、按「開始翻譯」，完成後按「下載中文版 PDF」。

### 命令列

```bash
python -m paper_translate paper.pdf              # 輸出 paper_zh.pdf
python -m paper_translate paper.pdf -o 中文版.pdf
python -m paper_translate paper.pdf --translate-references   # 連參考文獻也翻
```

## 翻譯引擎

| 引擎 | 品質 | 需要 |
|---|---|---|
| `claude`（推薦） | 最好，術語正確、語句通順，懂學術寫作 | Anthropic API key |
| `google` | 普通，偏直譯 | 不用設定，免費 |

使用 Claude 時要先設定 API key（到 <https://console.anthropic.com> 申請）：

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
```

有設定 key 就會自動使用 Claude，否則用 Google 翻譯。也可以用 `-b claude` / `-b google` 指定。

其他環境變數：

- `PAPER_TRANSLATE_MODEL`：Claude 模型（預設 `claude-opus-5-5`）
- `PAPER_TRANSLATE_EFFORT`：`low` / `medium` / `high`（預設 `medium`，越高越仔細也越貴）

## 運作原理

1. **擷取**：用 PyMuPDF 讀出每個文字區塊的位置、字級、顏色
2. **翻譯**：分批送去翻譯，同時附上標題與摘要當作上下文，讓術語一致
3. **排版**：只抹除原本的英文文字（圖片和向量圖形完全不動），再把中文放回同一個框裡；中文放不下時會自動縮小字級，不會蓋到旁邊的內容

刻意保留不翻的內容：

- 數學式、純數字、表格裡的數值
- 圖表內的短標籤（例如座標軸「Acc (%)」），可用 `--translate-figure-text` 打開
- 參考文獻列表，可用 `--translate-references` 打開

## 限制

- **掃描版 PDF**（整頁都是圖片）沒有文字可抓，需要先做 OCR
- 內嵌在文字中的行內數學式會跟著段落一起送去翻譯，Claude 會保留符號，但字型會換成一般字型
- 預設使用 PyMuPDF 內建的中文字型（黑體）。想要明體可以下載 [Noto Serif TC](https://fonts.google.com/noto/specimen/Noto+Serif+TC)，再用 `--font NotoSerifTC-Regular.ttf` 指定

## 測試

```bash
python tests/test_pipeline.py
```

測試會產生一份範例論文，用離線的假翻譯器跑完整流程，檢查圖片、圖形與表格位置都沒有變。
