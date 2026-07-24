"""Tests for ATS-safe single-column CV PDF export."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

from backend.generation.cv_pdf import generate_cv_variant_pdf


def test_generate_cv_variant_pdf_creates_nonempty_file_with_name(tmp_path: Path):
    text = (
        "# Gabriel Strecker\n\n"
        "## Profil\n"
        "Ausrichtung: Technical Product Manager.\n\n"
        "## Berufserfahrung\n"
        "- Beispiel-Bullet mit Umlauten: Fähigkeit, Größe, Größe.\n"
    )
    out = tmp_path / "cv_ats.pdf"
    path = generate_cv_variant_pdf(text, out)

    assert path == out
    assert path.is_file()
    assert path.stat().st_size > 0

    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(str(path)).pages
    )
    assert "Gabriel Strecker" in extracted
    assert "Technical Product Manager" in extracted or "Ausrichtung" in extracted
    # Markdown heading markers should not appear as raw hashes in body sense;
    # name line remains without requiring '#'.
    assert "# Gabriel" not in extracted


def test_generate_cv_variant_pdf_accepts_plain_text(tmp_path: Path):
    plain = (
        "Gabriel Strecker\n\n"
        "Profil:\n"
        "Ausrichtung: AI Product Manager.\n"
    )
    path = generate_cv_variant_pdf(plain, tmp_path / "plain.pdf")
    assert path.stat().st_size > 0
    extracted = PdfReader(str(path)).pages[0].extract_text() or ""
    assert "Gabriel Strecker" in extracted


def test_write_passed_cv_emits_pdf_sibling(tmp_path: Path):
    from backend.generation.watchlist_cv import write_passed_cv_from_row

    row = {
        "url": "https://example.jobs.personio.de/job/1",
        "title": "AI Product Manager",
        "job": {
            "title": "AI Product Manager",
            "jd_text": "AI Product Manager role",
            "url": "https://example.jobs.personio.de/job/1",
            "location": None,
            "work_mode": None,
            "employment_type": None,
            "source": "personio",
            "fetched_at": "2026-01-01T00:00:00+00:00",
        },
        "fit_check": {"top_score": 76},
    }
    with patch(
        "backend.generation.watchlist_cv._passed_plan_and_bodies",
        return_value=(
            "# Gabriel Strecker\n\n## Profil\nAusrichtung: TPM.\n",
            "Gabriel Strecker\n\nProfil:\nAusrichtung: TPM.\n",
        ),
    ):
        md_path = write_passed_cv_from_row(row, tmp_path)

    pdf_path = md_path.with_suffix(".pdf")
    assert pdf_path.is_file()
    assert pdf_path.stat().st_size > 0
    extracted = PdfReader(str(pdf_path)).pages[0].extract_text() or ""
    assert "Gabriel Strecker" in extracted
