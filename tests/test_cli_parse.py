from __future__ import annotations

import pytest
import typer

from benchmark.cli import _parse_scenarios
from benchmark.generate.records import PayloadProfile


def test_parse_scenarios_all_expands_three() -> None:
    assert _parse_scenarios("all") == [
        PayloadProfile.small,
        PayloadProfile.medium,
        PayloadProfile.large,
    ]


def test_parse_scenarios_comma_separated() -> None:
    assert _parse_scenarios(" small , evolution ") == [
        PayloadProfile.small,
        PayloadProfile.evolution,
    ]


def test_parse_scenarios_single() -> None:
    assert _parse_scenarios("medium") == [PayloadProfile.medium]


def test_parse_scenarios_map_heavy() -> None:
    assert _parse_scenarios("map_heavy") == [PayloadProfile.map_heavy]


def test_parse_scenarios_empty_raises() -> None:
    with pytest.raises(typer.BadParameter):
        _parse_scenarios("  ")
