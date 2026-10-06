from pathlib import Path

import pytest


@pytest.fixture
def fixture_raw_root() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_run_id() -> str:
    return "20260101T000000Z-normal-abcdef"
