"""Provenance of generated outputs: git blobs and commits, and library versions."""

from __future__ import annotations

import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

LIBRARIES = ("numpy", "pandas", "rasterio", "httpx", "pydantic", "pystac-client", "matplotlib")


def git(*args: str) -> str:
    """Run a git command and return its trimmed output.

    Args:
        *args: Git arguments, e.g. ``("rev-parse", "HEAD")``.

    Returns:
        The output, or ``"unknown"`` when git is missing or the command fails.
    """
    try:
        done = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return done.stdout.strip() or "unknown"


def blob(path: Path) -> str:
    """The git blob hash of a file (what ``git hash-object`` prints).

    Args:
        path: The file.

    Returns:
        The hash, or ``"unknown"``.
    """
    return git("hash-object", str(path))


def last_commit(path: Path) -> str:
    """The last commit that changed a file.

    Args:
        path: The file.

    Returns:
        The commit hash, or ``"unknown"``.
    """
    return git("log", "-1", "--format=%H", "--", str(path))


def head() -> str:
    """The checked-out commit.

    Returns:
        The commit hash, or ``"unknown"``.
    """
    return git("rev-parse", "HEAD")


def library_versions(names: tuple[str, ...] = LIBRARIES) -> dict[str, str]:
    """Installed versions of the libraries that shape the numbers.

    Args:
        names: Distribution names.

    Returns:
        Version by name (``"not installed"`` when missing).
    """
    versions = {}
    for name in names:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = "not installed"
    return versions
