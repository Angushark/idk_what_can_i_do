"""Command line: python -m paper_translate paper.pdf [-o paper_zh.pdf]"""

import argparse
import sys
from pathlib import Path

from .core import Options, translate_pdf
from .translators import get_translator


def main() -> None:
    ap = argparse.ArgumentParser(description="把英文論文 PDF 翻譯成繁體中文，保留原本版面、圖片與表格位置。")
    ap.add_argument("input", help="英文論文 PDF")
    ap.add_argument("-o", "--output", help="輸出檔名（預設：<原檔名>_zh.pdf）")
    ap.add_argument("-b", "--backend", choices=["claude", "google", "fake"],
                    help="翻譯引擎（預設：有 ANTHROPIC_API_KEY 用 claude，否則用 google）")
    ap.add_argument("--font", help="自訂中文字型檔（.ttf/.otf），例如 NotoSerifTC-Regular.ttf")
    ap.add_argument("--translate-references", action="store_true", help="連參考文獻也翻譯")
    ap.add_argument("--translate-figure-text", action="store_true", help="翻譯圖表內的短標籤")
    ap.add_argument("--workers", type=int, default=4, help="同時翻譯的批次數")
    args = ap.parse_args()

    src = Path(args.input)
    dst = Path(args.output) if args.output else src.with_name(src.stem + "_zh.pdf")
    opts = Options(
        translate_references=args.translate_references,
        translate_figure_text=args.translate_figure_text,
        workers=args.workers,
        font_file=args.font,
    )
    translator = get_translator(args.backend)
    print(f"翻譯引擎：{translator.name}")

    def progress(msg: str, frac: float) -> None:
        print(f"\r[{frac * 100:5.1f}%] {msg}        ", end="", flush=True)

    try:
        translate_pdf(src, dst, translator, opts, progress)
    except Exception as e:
        print(f"\n錯誤：{e}", file=sys.stderr)
        sys.exit(1)
    print(f"\n完成：{dst}")


if __name__ == "__main__":
    main()
