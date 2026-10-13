"""Web UI: upload an English paper PDF, download the Traditional Chinese version.

Run:  python -m paper_translate.web   then open http://127.0.0.1:5000
"""

from __future__ import annotations

import os
import tempfile
import threading
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

from .core import Options, translate_pdf
from .translators import get_translator

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB
WORK_DIR = Path(tempfile.gettempdir()) / "paper_translate"
WORK_DIR.mkdir(exist_ok=True)

jobs: dict[str, dict] = {}


def _run(job_id: str, src: Path, dst: Path, backend: str, opts: Options) -> None:
    job = jobs[job_id]

    def progress(msg: str, frac: float) -> None:
        job.update(message=msg, progress=frac)

    try:
        translate_pdf(src, dst, get_translator(backend or None), opts, progress)
        job.update(status="done", message="完成", progress=1.0)
    except Exception as e:
        job.update(status="error", message=str(e))
    finally:
        src.unlink(missing_ok=True)


@app.get("/")
def index():
    default = "claude" if os.environ.get("ANTHROPIC_API_KEY") else "google"
    return render_template("index.html", default_backend=default)


@app.post("/api/translate")
def start():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".pdf"):
        return jsonify(error="請上傳 PDF 檔"), 400
    job_id = uuid.uuid4().hex
    src = WORK_DIR / f"{job_id}.pdf"
    dst = WORK_DIR / f"{job_id}_zh.pdf"
    f.save(src)
    name = Path(f.filename).stem + "_zh.pdf"
    opts = Options(
        translate_references=request.form.get("references") == "on",
        translate_figure_text=request.form.get("figure_text") == "on",
    )
    jobs[job_id] = {"status": "running", "message": "排隊中", "progress": 0.0, "path": dst, "name": name}
    threading.Thread(target=_run, args=(job_id, src, dst, request.form.get("backend", ""), opts),
                     daemon=True).start()
    return jsonify(job_id=job_id)


@app.get("/api/status/<job_id>")
def status(job_id: str):
    job = jobs.get(job_id) or abort(404)
    return jsonify({k: job[k] for k in ("status", "message", "progress")})


@app.get("/api/download/<job_id>")
def download(job_id: str):
    job = jobs.get(job_id) or abort(404)
    if job["status"] != "done":
        abort(409)
    return send_file(job["path"], as_attachment=True, download_name=job["name"], mimetype="application/pdf")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)))
