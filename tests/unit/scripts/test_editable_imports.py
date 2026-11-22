"""Tests for the reordering of the import finders in a meson-python editable install."""

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import pytest
from scripts import editable_imports


class FakeMesonFinder:
    """Stands for the finder that the editable install of meson-python puts first in sys.meta_path."""


def test_without_an_editable_install_nothing_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(editable_imports, "EDITABLE_LOADER", "no_such_editable_loader_module")
    path_before, finders_before = list(sys.path), list(sys.meta_path)
    assert not editable_imports.prefer_source_tree(Path("/project/src"))
    assert sys.path == path_before
    assert sys.meta_path == finders_before


def test_the_meson_finder_moves_behind_the_path_finder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    loader = importlib.util.module_from_spec(importlib.machinery.ModuleSpec("fake_editable_loader", None))
    loader.MesonpyMetaFinder = FakeMesonFinder  # pyrefly: ignore[missing-attribute] -- a module object takes any attribute, as the real loader module defines this class
    monkeypatch.setitem(sys.modules, "fake_editable_loader", loader)
    monkeypatch.setattr(editable_imports, "EDITABLE_LOADER", "fake_editable_loader")
    meson_finder = FakeMesonFinder()
    monkeypatch.setattr(sys, "meta_path", [meson_finder, *sys.meta_path])
    monkeypatch.setattr(sys, "path", list(sys.path))
    assert editable_imports.prefer_source_tree(tmp_path)
    assert sys.path[0] == str(tmp_path)
    assert sys.meta_path[-1] is meson_finder
    assert sys.meta_path[0] is not meson_finder
