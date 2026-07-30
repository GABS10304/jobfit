"""Tests for best-effort salary extraction and the min-salary gate."""

from backend.sourcing.salary_filter import extract_salary_range, passes_salary_gate


def test_extract_salary_range_none_without_figure():
    assert extract_salary_range("Wir suchen einen Product Manager mit 5 Jahren Erfahrung.") is None
    assert extract_salary_range(None) is None
    assert extract_salary_range("") is None


def test_extract_salary_range_dash_with_currency():
    assert extract_salary_range("Gehalt: 70.000 - 90.000 €") == (70000.0, 90000.0)


def test_extract_salary_range_currency_after_each_number():
    assert extract_salary_range("70.000€ - 90.000€ je nach Erfahrung") == (70000.0, 90000.0)


def test_extract_salary_range_bis_and_euro_word():
    assert extract_salary_range("Bruttojahresgehalt 70.000 bis 90.000 Euro") == (70000.0, 90000.0)


def test_extract_salary_range_k_shorthand():
    assert extract_salary_range("75k - 90k EUR Jahresgehalt") == (75000.0, 90000.0)


def test_extract_salary_range_single_figure_with_currency():
    assert extract_salary_range("Wir bieten 80.000 € Jahresgehalt.") == (80000.0, 80000.0)


def test_extract_salary_range_single_figure_with_context_word():
    assert extract_salary_range("Jahresgehalt liegt bei 80.000, verhandelbar.") == (
        80000.0,
        80000.0,
    )


def test_passes_salary_gate_no_floor_set():
    assert passes_salary_gate("egal was hier steht", None) is True


def test_passes_salary_gate_no_figure_in_jd_fails_open():
    assert passes_salary_gate("Keine Gehaltsangabe in dieser Anzeige.", 90000) is True


def test_passes_salary_gate_below_floor_rejected():
    assert passes_salary_gate("Gehalt: 60.000 - 70.000 €", 90000) is False


def test_passes_salary_gate_range_overlaps_floor_passes():
    # Upper bound of the range is what counts — a job might negotiate up.
    assert passes_salary_gate("Gehalt: 80.000 - 95.000 €", 90000) is True


def test_passes_salary_gate_above_floor_passes():
    assert passes_salary_gate("Gehalt: 95.000 - 110.000 €", 90000) is True
