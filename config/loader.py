"""Loading, resolving and fingerprinting the project configuration.

The loader is the single place that:
  * finds the repository root,
  * reads ``.env`` so that secrets such as the GEE project ID are available
    from the environment and never from a tracked file,
  * validates ``config.yaml`` against :mod:`config.schema`,
  * produces a stable config hash for the ``runs`` table (brief, Section 10).
"""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

import yaml

from config.schema import Config

#: Environment variable that may point at an alternative config file.
CONFIG_PATH_ENV_VAR = "HDM_CONFIG"

#: Default config location, relative to the repository root.
DEFAULT_CONFIG_RELPATH = Path("config/config.yaml")


class ConfigError(RuntimeError):
    """Raised when the configuration cannot be found, parsed or validated."""


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Absolute path to the repository root.

    Derived from this file's location (``<root>/config/loader.py``) rather than
    from the current working directory, so that imports behave the same whether
    the code is run from the root, from a test, or from a notebook.
    """
    return Path(__file__).resolve().parent.parent


def load_dotenv_if_present(root: Path | None = None) -> Path | None:
    """Load ``<root>/.env`` into ``os.environ`` if it exists.

    Existing environment variables win, so an explicitly exported value is never
    overwritten by the file. Returns the path loaded, or ``None``.
    """
    root = Path(root) if root is not None else repo_root()
    env_path = root / ".env"
    if not env_path.is_file():
        return None
    try:
        from dotenv import load_dotenv
    except ImportError as exc:  # pragma: no cover - environment problem
        raise ConfigError(
            "python-dotenv is not installed; create the conda environment with "
            "`conda env create -f environment.yml`"
        ) from exc
    load_dotenv(env_path, override=False)
    return env_path


def config_path(explicit: str | Path | None = None) -> Path:
    """Resolve which config file to use.

    Precedence: explicit argument, then ``$HDM_CONFIG``, then the default.
    """
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    from_env = os.environ.get(CONFIG_PATH_ENV_VAR)
    if from_env:
        return Path(from_env).expanduser().resolve()
    return (repo_root() / DEFAULT_CONFIG_RELPATH).resolve()


#: Where per-site overlays live, relative to the repository root.
SITES_RELPATH = Path("config/sites")


def deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge ``overlay`` over ``base``, returning a new dict.

    Nested mappings are merged key by key; anything else replaces wholesale.
    A list is replaced rather than concatenated, because every list in this
    configuration is a complete specification -- band lists, SCL class codes,
    scale endpoints -- and appending to one would silently produce something
    nobody wrote.
    """
    merged = dict(base)
    for key, value in overlay.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config_with_overlay(
    overlay: str | Path | dict,
    *,
    base: str | Path | None = None,
    load_env: bool = True,
) -> Config:
    """Validate the base config with a small overlay merged over it.

    This is how a validation event or an alternative AOI is run without
    copying the whole configuration. A copy would duplicate every threshold in
    the project, and the duplicates would drift the first time one was tuned --
    so an overlay carries only what differs, usually ``aoi`` and ``dates``.

    Args:
        overlay: a dict, or a path to a small YAML file. A bare name such as
            ``"baige_2018"`` is looked up in ``config/sites/``.
        base: the configuration to merge over. Defaults as ``load_config``.

    Raises:
        ConfigError: if either file is missing or the merged result fails
            validation -- the merged config is validated in full, so an
            overlay cannot introduce a key the schema does not accept.
    """
    if load_env:
        load_dotenv_if_present()

    resolved_base = config_path(base)
    if not resolved_base.is_file():
        raise ConfigError(f"config file not found: {resolved_base}")
    with resolved_base.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ConfigError(f"config file is not a YAML mapping: {resolved_base}")

    if isinstance(overlay, dict):
        patch = overlay
        source = "<dict>"
    else:
        candidate = Path(overlay)
        if not candidate.suffix:
            candidate = repo_root() / SITES_RELPATH / f"{candidate.name}.yaml"
        candidate = candidate.expanduser().resolve()
        if not candidate.is_file():
            raise ConfigError(f"overlay file not found: {candidate}")
        with candidate.open("r", encoding="utf-8") as fh:
            patch = yaml.safe_load(fh)
        if not isinstance(patch, dict):
            raise ConfigError(f"overlay is not a YAML mapping: {candidate}")
        source = str(candidate)

    merged = deep_merge(raw, patch)
    try:
        config = Config.model_validate(merged)
    except Exception as exc:
        raise ConfigError(
            f"configuration invalid after merging overlay {source} over "
            f"{resolved_base}: {exc}"
        ) from exc
    return config


def available_sites(root: Path | None = None) -> list[str]:
    """Names of the per-site overlays in ``config/sites``."""
    base = (Path(root) if root is not None else repo_root()) / SITES_RELPATH
    if not base.is_dir():
        return []
    return sorted(p.stem for p in base.glob("*.yaml"))


def load_config(path: str | Path | None = None, *, load_env: bool = True) -> Config:
    """Read and validate the configuration.

    Args:
        path: Explicit config file. Defaults to ``$HDM_CONFIG`` or
            ``config/config.yaml``.
        load_env: Also load ``.env`` into the environment. Disable in tests that
            must not see the developer's real credentials.

    Raises:
        ConfigError: if the file is missing, is not a YAML mapping, or fails
            schema validation. The underlying Pydantic error is chained so the
            offending key and reason stay visible.
    """
    if load_env:
        load_dotenv_if_present()

    resolved = config_path(path)
    if not resolved.is_file():
        raise ConfigError(f"config file not found: {resolved}")

    with resolved.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        raise ConfigError(f"config file is empty: {resolved}")
    if not isinstance(raw, dict):
        raise ConfigError(
            f"config file must contain a YAML mapping at the top level, "
            f"got {type(raw).__name__}: {resolved}"
        )

    try:
        return Config.model_validate(raw)
    except Exception as exc:
        raise ConfigError(f"invalid configuration in {resolved}:\n{exc}") from exc


def resolved_paths(cfg: Config, root: Path | None = None) -> dict[str, Path]:
    """Configured directories as absolute paths."""
    return cfg.paths.absolute(root if root is not None else repo_root())


def ensure_output_dirs(cfg: Config, root: Path | None = None) -> dict[str, Path]:
    """Create every configured directory that does not yet exist."""
    paths = resolved_paths(cfg, root)
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


def config_hash(cfg: Config) -> str:
    """Stable SHA-256 fingerprint of the configuration.

    Stored with each run (brief, Section 10: ``runs.config_hash``) so that any
    stored result can be tied back to the exact settings that produced it.
    Keys are sorted, so reordering ``config.yaml`` does not change the hash --
    only a change in values does.
    """
    payload = json.dumps(
        cfg.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
