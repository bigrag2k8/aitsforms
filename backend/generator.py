"""Render the docxtpl templates and export PDFs via LibreOffice (headless).

LibreOffice is used (rather than Word COM) so the same code runs unchanged on a
Linux web host.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile

from docxtpl import DocxTemplate

from .models import TitleJob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates_docx")
OUTPUT = os.environ.get("TITLEAPP_OUTPUT_DIR", os.path.join(ROOT, "output"))

RE46_TPL = os.path.join(TEMPLATES, "re46_template.docx")
CHAIN_TPL = os.path.join(TEMPLATES, "re46_1_template.docx")

_SOFFICE_CANDIDATES = [
    os.environ.get("SOFFICE_PATH", ""),
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/opt/libreoffice/program/soffice",
    "soffice",
]


def find_soffice() -> str | None:
    for c in _SOFFICE_CANDIDATES:
        if not c:
            continue
        if os.path.isabs(c) and os.path.exists(c):
            return c
        if not os.path.isabs(c) and shutil.which(c):
            return c
    return None


def render_docx(template_path: str, context: dict, out_path: str) -> str:
    tpl = DocxTemplate(template_path)
    tpl.render(context)
    tpl.save(out_path)
    return out_path


def docx_to_pdf(docx_path: str, out_dir: str) -> str | None:
    """Convert a .docx to .pdf. Returns the pdf path, or None if unavailable."""
    soffice = find_soffice()
    if not soffice:
        return None
    profile = tempfile.mkdtemp(prefix="lo_profile_")
    profile_uri = "file:///" + profile.replace("\\", "/")
    try:
        subprocess.run(
            [
                soffice,
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf:writer_pdf_Export",
                "--outdir",
                out_dir,
                docx_path,
                f"-env:UserInstallation={profile_uri}",
            ],
            check=True,
            timeout=120,
            capture_output=True,
        )
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    pdf = os.path.join(out_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
    return pdf if os.path.exists(pdf) else None


def generate(job: TitleJob, job_id: str, want_pdf: bool = True) -> dict:
    """Render both forms for a job. Returns a dict of produced file paths."""
    out_dir = os.path.join(OUTPUT, job_id)
    os.makedirs(out_dir, exist_ok=True)
    ctx = job.context()

    stem = _safe_stem(job)
    re46_docx = render_docx(RE46_TPL, ctx, os.path.join(out_dir, f"RE46_{stem}.docx"))
    chain_docx = render_docx(CHAIN_TPL, ctx, os.path.join(out_dir, f"RE46-1_{stem}.docx"))

    result = {"re46_docx": re46_docx, "chain_docx": chain_docx, "re46_pdf": None, "chain_pdf": None}
    if want_pdf:
        result["re46_pdf"] = docx_to_pdf(re46_docx, out_dir)
        result["chain_pdf"] = docx_to_pdf(chain_docx, out_dir)
    return result


def _safe_stem(job: TitleJob) -> str:
    raw = "_".join(p for p in [job.parcel, job.suffix] if p) or "form"
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw)
