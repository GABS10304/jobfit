"""ATS text-layer verification for generated application PDFs.

Checks what an ATS parser actually sees — the PDF's embedded text layer,
extracted via pypdf — rather than the source markdown. fpdf2's single-column
layout can't orphan/overflow the way multi-column templates can, but it can
still silently emit a garbled or empty text layer (font/encoding bugs), and a
selected bullet can get cut between markdown and PDF. This module catches
that class of bug; it does not re-decide what's relevant — that's already
decided deterministically upstream by selection_plan.py / the fit-engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from backend.signal_lexicon import candidates_for_signal


def _phrase_in_text(phrase: str, haystack: str) -> bool:
    if not phrase:
        return False
    if len(phrase) <= 3:
        pattern = rf"(?<![a-z0-9äöüß_]){re.escape(phrase)}(?![a-z0-9äöüß_])"
        return re.search(pattern, haystack) is not None
    return phrase in haystack


@dataclass
class AtsCheckResult:
    page_count: int
    extracted_chars: int
    name_found: bool
    location_found: bool
    signals_found: list[str]
    signals_missing: list[str]
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.warnings

    def to_dict(self) -> dict:
        return {
            "page_count": self.page_count,
            "extracted_chars": self.extracted_chars,
            "name_found": self.name_found,
            "location_found": self.location_found,
            "signals_found": self.signals_found,
            "signals_missing": self.signals_missing,
            "warnings": self.warnings,
            "passed": self.passed,
        }


def extract_pdf_text(pdf_path: Path | str) -> tuple[str, int]:
    """Extract the PDF's actual text layer (what an ATS parser sees)."""
    reader = PdfReader(str(pdf_path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages), len(pages)


def check_application_pdf(
    pdf_path: Path | str,
    *,
    person_name: str,
    person_location: str | None = None,
    matched_signals: list[str] | None = None,
) -> AtsCheckResult:
    """Verify the rendered PDF text layer, not the source markdown.

    Confirms identity details survive to literal, extractable text and that
    the signals selection_plan.py already matched against the JD actually
    landed in the rendered output.
    """
    text, page_count = extract_pdf_text(pdf_path)
    normalized = text.casefold()
    warnings: list[str] = []

    if not text.strip():
        warnings.append(
            "PDF liefert keinen extrahierbaren Text (leerer oder reiner Bild-Textlayer)."
        )

    name_found = bool(person_name) and person_name.strip().casefold() in normalized
    if person_name and not name_found:
        warnings.append(f"Name '{person_name}' nicht im extrahierten PDF-Text gefunden.")

    location_found = True
    if person_location:
        # Full string or just the city (first segment) — not every comma part,
        # since a bare country name (e.g. "Deutschland") would match almost
        # any German CV and defeat the check.
        first_part = person_location.split(",")[0].strip()
        candidates = [c for c in {person_location.strip(), first_part} if c]
        location_found = any(c.casefold() in normalized for c in candidates)
        if not location_found:
            warnings.append(
                f"Ort '{person_location}' nicht im extrahierten PDF-Text gefunden."
            )

    signals_found: list[str] = []
    signals_missing: list[str] = []
    for signal in matched_signals or []:
        hit = any(
            _phrase_in_text(candidate, normalized)
            for candidate in candidates_for_signal(signal)
        )
        (signals_found if hit else signals_missing).append(signal)
    if signals_missing:
        warnings.append(
            "Gematchte Signale fehlen im gerenderten PDF-Text: "
            + ", ".join(signals_missing)
        )

    return AtsCheckResult(
        page_count=page_count,
        extracted_chars=len(text),
        name_found=name_found,
        location_found=location_found,
        signals_found=signals_found,
        signals_missing=signals_missing,
        warnings=warnings,
    )
