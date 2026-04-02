"""Tests for textual_diff_view."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual import containers

from textual_diff_view import DiffView, LoadError
from textual_diff_view._diff_view import fill_lists


# --- fill_lists ---


def test_fill_lists_equal_length():
    a = [1, 2, 3]
    b = [4, 5, 6]
    fill_lists(a, b, 0)
    assert a == [1, 2, 3]
    assert b == [4, 5, 6]


def test_fill_lists_a_longer():
    a = [1, 2, 3]
    b = [4]
    fill_lists(a, b, 0)
    assert len(a) == len(b) == 3
    assert b == [4, 0, 0]


def test_fill_lists_b_longer():
    a = [1]
    b = [4, 5, 6]
    fill_lists(a, b, 0)
    assert len(a) == len(b) == 3
    assert a == [1, 0, 0]


def test_fill_lists_both_empty():
    a: list = []
    b: list = []
    fill_lists(a, b, 0)
    assert a == []
    assert b == []


# --- DiffView (logic only, no app) ---


CODE_A = """\
def hello():
    print("hello")
"""

CODE_B = """\
def hello():
    print("hello, world")
"""

CODE_IDENTICAL = """\
def hello():
    pass
"""


def make_diff_view(original: str = CODE_A, modified: str = CODE_B) -> DiffView:
    return DiffView("original.py", "modified.py", original, modified)


def test_diff_view_counts_change():
    dv = make_diff_view()
    additions, removals = dv.counts
    assert additions >= 1
    assert removals >= 1


def test_diff_view_counts_identical():
    dv = make_diff_view(CODE_IDENTICAL, CODE_IDENTICAL)
    additions, removals = dv.counts
    assert additions == 0
    assert removals == 0


def test_diff_view_counts_only_additions():
    original = "line1\n"
    modified = "line1\nline2\n"
    dv = make_diff_view(original, modified)
    additions, removals = dv.counts
    assert additions >= 1
    assert removals == 0


def test_diff_view_counts_only_removals():
    original = "line1\nline2\n"
    modified = "line1\n"
    dv = make_diff_view(original, modified)
    additions, removals = dv.counts
    assert additions == 0
    assert removals >= 1


def test_grouped_opcodes_identical():
    dv = make_diff_view(CODE_IDENTICAL, CODE_IDENTICAL)
    # Identical files produce no groups (nothing to diff)
    assert dv.grouped_opcodes == []


def test_grouped_opcodes_changed():
    dv = make_diff_view()
    assert len(dv.grouped_opcodes) > 0


def test_tabs_expanded():
    code_with_tabs = "def foo():\n\tpass\n"
    dv = DiffView("a.py", "b.py", code_with_tabs, code_with_tabs)
    assert "\t" not in dv.code_original
    assert "\t" not in dv.code_modified


# --- DiffView.load (async) ---


@pytest.mark.asyncio
async def test_load_raises_load_error_for_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.py"
    with pytest.raises(LoadError):
        await DiffView.load(missing, missing)


@pytest.mark.asyncio
async def test_load_from_files(tmp_path):
    f1 = tmp_path / "original.py"
    f2 = tmp_path / "modified.py"
    f1.write_text(CODE_A, encoding="utf-8")
    f2.write_text(CODE_B, encoding="utf-8")
    dv = await DiffView.load(f1, f2)
    assert isinstance(dv, DiffView)
    assert dv.code_original == CODE_A.expandtabs()
    assert dv.code_modified == CODE_B.expandtabs()


# --- DiffView inside a Textual App ---


class _DiffApp(App):
    def __init__(self, original: str, modified: str) -> None:
        super().__init__()
        self._original = original
        self._modified = modified

    def compose(self) -> ComposeResult:
        with containers.VerticalScroll():
            yield DiffView("a.py", "b.py", self._original, self._modified)


@pytest.mark.asyncio
async def test_diff_view_mounts():
    app = _DiffApp(CODE_A, CODE_B)
    async with app.run_test(size=(120, 40)):
        assert app.query_one(DiffView) is not None
