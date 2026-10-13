"""Translate a PDF paper in place: same pages, same figures/tables, text replaced by Chinese.

Pipeline:
  1. extract  - collect text blocks (with position, size, color) from every page
  2. translate - send blocks to a translator in batches (concurrently)
  3. render   - redact the original text (images and vector graphics untouched),
                then typeset the translation inside the same rectangle, shrinking
                the font if needed so it never overflows into neighbouring content
"""

from __future__ import annotations

import html
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pymupdf

from .translators import Translator

REFERENCE_HEADINGS = re.compile(r"^\s*(\d+\.?\s*)?(references|bibliography|參考文獻)\s*$", re.I)
WORD = re.compile(r"[A-Za-z]{2,}")

ProgressFn = Callable[[str, float], None]


@dataclass
class Block:
    page: int
    rect: pymupdf.Rect
    text: str
    size: float
    color: int
    bold: bool
    translation: str | None = None


@dataclass
class Options:
    translate_references: bool = False   # reference lists are usually best left in English
    translate_figure_text: bool = False  # short labels inside figures / tables
    batch_chars: int = 6000
    workers: int = 4
    font_file: str | None = None         # optional .ttf/.otf, e.g. Noto Serif TC
    font_scale: float = 0.95             # CJK glyphs look larger than Latin at the same size


def _join_lines(lines: list[str]) -> str:
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not out:
            out = line
        elif out.endswith("-") and line[:1].islower():
            out = out[:-1] + line  # de-hyphenate "net-\nwork"
        else:
            out += " " + line
    return out


def _figure_regions(page: pymupdf.Page) -> tuple[list[pymupdf.Rect], list[pymupdf.Rect]]:
    images = [pymupdf.Rect(info["bbox"]) for info in page.get_image_info()]
    try:
        drawings = [r for r in page.cluster_drawings() if r.width > 30 and r.height > 30]
    except Exception:
        drawings = []
    return images, drawings


def _inside(rect: pymupdf.Rect, regions: list[pymupdf.Rect]) -> bool:
    for r in regions:
        inter = rect & r
        if not inter.is_empty and inter.get_area() >= 0.8 * rect.get_area():
            return True
    return False


def _is_tabular(lines: list[dict]) -> bool:
    """True when some lines sit side by side (table cells) instead of stacking like a paragraph."""
    for i, a in enumerate(lines):
        ra = pymupdf.Rect(a["bbox"])
        for b in lines[i + 1:]:
            rb = pymupdf.Rect(b["bbox"])
            v_overlap = min(ra.y1, rb.y1) - max(ra.y0, rb.y0)
            if v_overlap > 0.5 * min(ra.height, rb.height) and (rb.x0 >= ra.x1 or ra.x0 >= rb.x1):
                return True
    return False


def _make_block(pno: int, lines: list[dict]) -> Block | None:
    texts, sizes, colors, bold_chars, total_chars = [], [], [], 0, 0
    rect = pymupdf.Rect()
    for line in lines:
        texts.append("".join(s["text"] for s in line["spans"]))
        rect |= line["bbox"]
        for s in line["spans"]:
            n = len(s["text"].strip())
            if not n:
                continue
            sizes.extend([s["size"]] * n)
            colors.append(s["color"])
            total_chars += n
            if s["flags"] & 16 or "bold" in s["font"].lower():
                bold_chars += n
    text = _join_lines(texts)
    if not text or not sizes:
        return None
    return Block(
        page=pno,
        rect=rect,
        text=text,
        size=statistics.median(sizes),
        color=max(set(colors), key=colors.count),
        bold=bold_chars > total_chars / 2,
    )


def extract_blocks(doc: pymupdf.Document, opts: Options) -> list[Block]:
    blocks: list[Block] = []
    in_references = False
    for pno, page in enumerate(doc):
        images, drawings = _figure_regions(page)
        data = page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)
        for b in data["blocks"]:
            if b.get("type") != 0:
                continue
            # Skip rotated text, e.g. the arXiv side stamp.
            lines = [ln for ln in b["lines"] if abs(ln["dir"][1]) <= 0.01]
            # Table rows: translate each cell on its own so columns stay aligned.
            groups = [[ln] for ln in lines] if _is_tabular(lines) else [lines]
            for group in groups:
                blk = _make_block(pno, group)
                if blk is None:
                    continue
                if REFERENCE_HEADINGS.match(blk.text):
                    in_references = True
                    blocks.append(blk)
                    continue
                words = WORD.findall(blk.text)
                if not words:
                    continue  # numbers, equations, symbols
                if _inside(blk.rect, images):
                    continue
                if not opts.translate_figure_text and len(words) < 4 and _inside(blk.rect, drawings):
                    continue
                if in_references and not opts.translate_references:
                    continue
                blocks.append(blk)
    return blocks


def _batches(blocks: list[Block], max_chars: int) -> list[list[Block]]:
    batches, cur, n = [], [], 0
    for b in blocks:
        if cur and n + len(b.text) > max_chars:
            batches.append(cur)
            cur, n = [], 0
        cur.append(b)
        n += len(b.text)
    if cur:
        batches.append(cur)
    return batches


def translate_blocks(blocks: list[Block], translator: Translator, opts: Options,
                     progress: ProgressFn | None = None) -> None:
    # Title + abstract-ish opening gives the model the paper's topic and terminology.
    context = " ".join(b.text for b in blocks[:8])[:1500]
    batches = _batches(blocks, opts.batch_chars)
    done = 0

    def run(batch: list[Block]) -> None:
        nonlocal done
        results = translator.translate_batch([b.text for b in batch], context=context)
        for b, t in zip(batch, results):
            b.translation = t
        done += 1
        if progress:
            progress(f"翻譯中（{done}/{len(batches)} 批）", 0.1 + 0.8 * done / len(batches))

    with ThreadPoolExecutor(max_workers=max(1, opts.workers)) as pool:
        list(pool.map(run, batches))


def _css(opts: Options) -> tuple[str, pymupdf.Archive | None]:
    if opts.font_file:
        path = Path(opts.font_file)
        archive = pymupdf.Archive(str(path.parent))
        css = f"@font-face {{font-family: paperfont; src: url({path.name});}}\n* {{font-family: paperfont;}}"
        return css, archive
    # MuPDF falls back to its built-in CJK font for Chinese characters.
    return "* {font-family: sans-serif;}", None


def render(doc: pymupdf.Document, blocks: list[Block], opts: Options) -> None:
    base_css, archive = _css(opts)
    by_page: dict[int, list[Block]] = {}
    for b in blocks:
        if b.translation:
            by_page.setdefault(b.page, []).append(b)

    for pno, page_blocks in by_page.items():
        page = doc[pno]
        for b in page_blocks:
            page.add_redact_annot(b.rect)
        # Remove only the text; keep images and vector drawings (figures, table rules).
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        for b in page_blocks:
            size = b.size * opts.font_scale
            one_line = b.rect.height < b.size * 2.2
            body = html.escape(b.translation).replace("\n", "<br>")
            if b.bold:
                body = f"<b>{body}</b>"
            css = (base_css + f"\n* {{font-size: {size:.2f}px; line-height: 1.3; color: #{b.color:06x};"
                   f" text-align: {'left' if one_line else 'justify'}; margin: 0; padding: 0;}}")
            # A little extra width so short headings never wrap into a second line.
            rect = pymupdf.Rect(b.rect.x0, b.rect.y0, b.rect.x1 + (size if one_line else 0), b.rect.y1)
            # No <p> wrapper: its default margins would make MuPDF shrink single-line text.
            page.insert_htmlbox(rect, body, css=css, archive=archive, scale_low=0)


def translate_pdf(src: str | Path, dst: str | Path, translator: Translator,
                  opts: Options | None = None, progress: ProgressFn | None = None) -> Path:
    opts = opts or Options()
    doc = pymupdf.open(src)
    if progress:
        progress("分析版面中", 0.05)
    blocks = extract_blocks(doc, opts)
    if not blocks:
        raise ValueError("找不到可翻譯的文字，這份 PDF 可能是掃描檔（圖片），需要先做 OCR。")
    translate_blocks(blocks, translator, opts, progress)
    if progress:
        progress("排版輸出中", 0.92)
    render(doc, blocks, opts)
    doc.subset_fonts()  # embed only the Chinese glyphs actually used
    dst = Path(dst)
    doc.save(dst, garbage=3, deflate=True)
    doc.close()
    if progress:
        progress("完成", 1.0)
    return dst
