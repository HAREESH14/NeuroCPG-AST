"""Shared pytest fixtures for NeuroAST tests."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def bubble_sort_c() -> str:
    """Load the bubble sort C fixture as a string."""
    return (FIXTURES_DIR / "sample_bubble_sort.c").read_text()


@pytest.fixture
def bubble_sort_java() -> str:
    """Load the bubble sort Java fixture as a string."""
    return (FIXTURES_DIR / "sample_bubble_sort.java").read_text()
