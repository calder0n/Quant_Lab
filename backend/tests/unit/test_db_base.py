"""Tests for the declarative base."""

from quantlab.infrastructure.db.base import NAMING_CONVENTION, Base


def test_metadata_uses_deterministic_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert "pk" in NAMING_CONVENTION
    assert "fk" in NAMING_CONVENTION
