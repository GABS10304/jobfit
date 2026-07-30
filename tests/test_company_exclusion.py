"""Tests for company-name exclusion (constraints.excluded_companies)."""

from backend.sourcing.filtering import is_excluded_company


def test_is_excluded_company_fail_open_without_list():
    assert is_excluded_company("Acme GmbH", None) is False
    assert is_excluded_company("Acme GmbH", []) is False


def test_is_excluded_company_fail_open_without_name():
    assert is_excluded_company(None, ["Acme GmbH"]) is False
    assert is_excluded_company("", ["Acme GmbH"]) is False


def test_is_excluded_company_case_insensitive_exact_match():
    assert is_excluded_company("acme gmbh", ["Acme GmbH", "Foo Corp"]) is True
    assert is_excluded_company("Acme GmbH", ["acme gmbh"]) is True


def test_is_excluded_company_no_partial_match():
    # "Acme" alone must not exclude "Acme Solutions GmbH" — exact match only.
    assert is_excluded_company("Acme Solutions GmbH", ["Acme"]) is False


def test_is_excluded_company_not_in_list():
    assert is_excluded_company("Beta AG", ["Acme GmbH", "Foo Corp"]) is False
