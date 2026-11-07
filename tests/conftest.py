"""Shared pytest fixtures.

Any array or geometry constructed in ``tests/`` is SYNTHETIC -- hand-made test
data, never satellite imagery presented as real (brief, Section 2). Tests that
build such data are marked ``@pytest.mark.synthetic``; tests that assert against
real imagery are marked ``@pytest.mark.realdata``.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from config.loader import load_config, repo_root
from config.schema import Config


@pytest.fixture(scope="session")
def root() -> Path:
    """Repository root."""
    return repo_root()


@pytest.fixture(scope="session")
def cfg() -> Config:
    """The project's real configuration, validated.

    ``load_env=False``: the test suite must not depend on, or be influenced by,
    a developer's local ``.env``.
    """
    return load_config(load_env=False)


@pytest.fixture(scope="session")
def raw_config_dict(root: Path) -> dict[str, Any]:
    """``config.yaml`` parsed to a plain dict, for mutation in tests."""
    import yaml

    with (root / "config" / "config.yaml").open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture
def mutable_config(raw_config_dict: dict[str, Any]) -> dict[str, Any]:
    """A deep copy of the real config dict, safe to modify."""
    return copy.deepcopy(raw_config_dict)


@pytest.fixture
def write_config(tmp_path: Path):
    """Factory writing a config dict to a temporary YAML file."""
    import yaml

    def _write(data: dict[str, Any], name: str = "config.yaml") -> Path:
        path = tmp_path / name
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False)
        return path

    return _write
