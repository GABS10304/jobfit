"""Pin the V3 strict presence policy for tests that verify it.

domain/constraints.yaml runs remote_first_hybrid_ok in "flexible" mode since
2026-10-17 (Gabriel: hybrid with any number of office days is fine, full
presence is only reported). The V3 boundary tests still guard the strict
policy, which stays available via mode: strict.
"""

from __future__ import annotations

import pytest

from backend import data_loader

_original_load = data_loader.load_constraints


def _strict_load(path=None):
    constraints = _original_load(path)
    for hard in constraints.hard_constraints:
        if hard.id == "remote_first_hybrid_ok":
            hard.mode = "strict"
    return constraints


@pytest.fixture(autouse=True)
def strict_presence(monkeypatch):
    monkeypatch.setattr(data_loader, "load_constraints", _strict_load)
    data_loader.get_constraints.cache_clear()
    yield
    data_loader.get_constraints.cache_clear()
