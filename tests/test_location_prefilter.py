"""Tests for Workday/Personio location keyword prefilter."""

from backend.sourcing.personio import (
    JobListing,
    filter_listings_by_location,
    location_keyword_match,
)


def test_location_keyword_match_fail_open_without_keywords():
    assert location_keyword_match("New York", None) is True
    assert location_keyword_match("New York", []) is True


def test_location_keyword_match_fail_open_without_location():
    assert location_keyword_match(None, ["Germany", "Remote"]) is True
    assert location_keyword_match("", ["Germany"]) is True


def test_location_keyword_match_substring():
    assert location_keyword_match("Berlin, Germany", ["Germany", "Remote"]) is True
    assert location_keyword_match("Remote - US", ["Remote"]) is True
    assert location_keyword_match("New York, NY", ["Germany", "Remote"]) is False


def test_filter_listings_by_location_splits():
    listings = [
        JobListing(url="https://x/a", title="A", locations_text="New York"),
        JobListing(url="https://x/b", title="B", locations_text="München"),
        JobListing(url="https://x/c", title="C", locations_text=None),
    ]
    kept, rejected = filter_listings_by_location(
        listings, ["Germany", "München", "Remote"]
    )
    assert [x.url for x in kept] == ["https://x/b", "https://x/c"]
    assert len(rejected) == 1
    assert rejected[0]["reject_reason"] == "location_prefilter"
    assert rejected[0]["url"] == "https://x/a"
