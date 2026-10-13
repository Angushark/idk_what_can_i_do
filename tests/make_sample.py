"""Generate a small two-column sample paper (original text) with a figure, a chart and a table."""

import sys

import pymupdf

PARA = ("Neural networks have become a standard tool for learning representations from raw data. "
        "In this work we study how the depth of a model affects its ability to generalize when the "
        "amount of labeled data is limited. We show that a simple regularization scheme improves "
        "accuracy across several benchmarks [3, 7].")


def make(path: str) -> None:
    doc = pymupdf.open()
    for pno in range(2):
        page = doc.new_page(width=612, height=792)
        if pno == 0:
            page.insert_textbox(pymupdf.Rect(72, 50, 540, 80), "Depth and Generalization in Small-Data Regimes",
                                fontsize=16, fontname="hebo", align=1)
            page.insert_textbox(pymupdf.Rect(72, 82, 540, 96), "A. Author and B. Writer", fontsize=10, align=1)
        y = 110
        for col_x in (72, 316):
            cy = y
            page.insert_text((col_x, cy + 10), "1 Introduction" if col_x == 72 else "2 Method",
                             fontsize=11, fontname="hebo")
            cy += 18
            for _ in range(2):
                r = pymupdf.Rect(col_x, cy, col_x + 224, cy + 110)
                page.insert_textbox(r, PARA, fontsize=9.5, align=3)
                cy += 118
        # raster figure
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 60), 0)
        pix.set_rect(pix.irect, (70, 130, 200))
        page.insert_image(pymupdf.Rect(72, 400, 296, 512), pixmap=pix)
        page.insert_textbox(pymupdf.Rect(72, 516, 296, 545),
                            "Figure 1: Accuracy of the proposed model as a function of depth.", fontsize=8.5)
        # vector chart with short labels
        page.draw_rect(pymupdf.Rect(316, 400, 540, 512), color=(0, 0, 0))
        for i, h in enumerate((30, 60, 80, 50)):
            page.draw_rect(pymupdf.Rect(340 + i * 45, 500 - h, 365 + i * 45, 500), color=None, fill=(0.8, 0.3, 0.2))
        page.insert_text((320, 410), "Acc (%)", fontsize=7)
        # table
        rows = [("Method", "Top-1", "Params"), ("Baseline", "71.2", "11M"), ("Ours", "74.8", "11M")]
        for r_i, row in enumerate(rows):
            for c_i, cell in enumerate(row):
                page.insert_text((80 + c_i * 70, 590 + r_i * 16), cell, fontsize=9)
        for yy in (578, 594, 642):
            page.draw_line((72, yy), (296, yy))
        page.insert_textbox(pymupdf.Rect(72, 646, 296, 675),
                            "Table 1: Comparison with the baseline on the validation set.", fontsize=8.5)
        if pno == 1:
            page.insert_text((316, 590), "References", fontsize=11, fontname="hebo")
            page.insert_textbox(pymupdf.Rect(316, 598, 540, 640),
                                "[1] C. Doe. Learning deep features. Journal of Examples, 2019.", fontsize=8)
    doc.save(path)


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "sample.pdf")
