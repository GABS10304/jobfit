"""Tests for the optional profile-photo header (German CVs only)."""

from __future__ import annotations

from backend import data_loader
from backend.generation.cv_html import _PHOTO_PATH, _render_header_html


def test_header_omits_photo_for_english_language():
    cv_master = data_loader.load_cv_master()
    html = _render_header_html(cv_master, language="en")
    assert 'class="photo"' not in html


def test_header_includes_photo_for_german_when_asset_present():
    cv_master = data_loader.load_cv_master()
    html = _render_header_html(cv_master, language="de")
    if _PHOTO_PATH.is_file():
        assert 'class="photo"' in html
        assert "data:image/jpeg;base64," in html
    else:
        # domain/assets/ is gitignored — a fresh clone has no photo asset,
        # and the header must still render cleanly without one.
        assert 'class="photo"' not in html


def test_header_defaults_to_german_language():
    cv_master = data_loader.load_cv_master()
    default_html = _render_header_html(cv_master)
    de_html = _render_header_html(cv_master, language="de")
    assert default_html == de_html
