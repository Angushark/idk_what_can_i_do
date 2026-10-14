"""Offline end-to-end tests (no network): python tests/test_pipeline.py"""

import io
import sys
import time
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_sample import make  # noqa: E402
from paper_translate.core import Options, extract_blocks, translate_pdf  # noqa: E402
from paper_translate.translators import FakeTranslator  # noqa: E402

OUT = Path(__file__).parent / "output"


def _sample() -> Path:
    OUT.mkdir(exist_ok=True)
    src = OUT / "sample.pdf"
    make(str(src))
    return src


def test_layout_preserved():
    src = _sample()
    dst = translate_pdf(src, OUT / "sample_zh.pdf", FakeTranslator())
    a, b = pymupdf.open(src), pymupdf.open(dst)
    assert len(a) == len(b)
    for pa, pb in zip(a, b):
        assert pa.rect == pb.rect
        # images and vector drawings untouched
        assert [i["bbox"] for i in pa.get_image_info()] == [i["bbox"] for i in pb.get_image_info()]
        assert len(pa.get_drawings()) == len(pb.get_drawings())
        text = pb.get_text()
        assert "測試" in text
        assert "Neural networks" not in text
        assert "71.2" in text           # numbers in the table stay
        assert "Acc (%)" in text        # short figure labels stay


def test_references_kept():
    blocks = extract_blocks(pymupdf.open(_sample()), Options())
    assert not any("Journal of Examples" in b.text for b in blocks)
    blocks = extract_blocks(pymupdf.open(_sample()), Options(translate_references=True))
    assert any("Journal of Examples" in b.text for b in blocks)


def test_table_cells_split():
    blocks = extract_blocks(pymupdf.open(_sample()), Options())
    texts = [b.text for b in blocks if b.page == 0]
    assert "Method" in texts and "Baseline" in texts


def test_web_flow():
    from paper_translate.web import app

    client = app.test_client()
    data = {"file": (io.BytesIO(_sample().read_bytes()), "paper.pdf"), "backend": "fake"}
    job = client.post("/api/translate", data=data, content_type="multipart/form-data").get_json()["job_id"]
    for _ in range(100):
        s = client.get(f"/api/status/{job}").get_json()
        if s["status"] != "running":
            break
        time.sleep(0.1)
    assert s["status"] == "done", s
    r = client.get(f"/api/download/{job}")
    assert r.status_code == 200 and r.data[:4] == b"%PDF"
    assert "paper_zh.pdf" in r.headers["Content-Disposition"]


def test_google_waits_out_rate_limit():
    from concurrent.futures import ThreadPoolExecutor

    from deep_translator.exceptions import TooManyRequests

    from paper_translate.translators import GoogleTranslator

    start, calls = time.monotonic(), []

    class Blocked:  # refuses everything for the first 0.5 s, like Google after too many requests
        def translate(self, text):
            calls.append(text)
            if time.monotonic() - start < 0.5:
                raise TooManyRequests()
            return "譯文"

    g = GoogleTranslator()
    g._t, g.MIN_INTERVAL, g.BACKOFF = Blocked(), 0, (0.2, 0.2, 0.2, 0.2)
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda t: g.translate_batch([t]), ["a", "b", "c", "d"]))
    assert results == [["譯文"]] * 4
    assert len(calls) <= 4 + 3  # threads paused together instead of each hammering Google


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
