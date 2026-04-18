# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Textual Diff View — a terminal UI widget (`DiffView`) for displaying diffs, built on the Textual framework. Published to PyPI as `textual-diff-view`.

## Commands

```bash
# Run all tests
make test
# or: uv run pytest tests/

# Update visual snapshots
make update-snapshots
# or: uv run pytest tests/ --snapshot-update

# Run a single test
uv run pytest tests/test_diff_view.py::test_name

# Run example app
uv run python examples/tdiff.py examples/example1.rs examples/example2.rs
```

## Architecture

The entire widget lives in `src/textual_diff_view/_diff_view.py`. Public API is just `DiffView` and `LoadError`, exported from `__init__.py`.

**Widget hierarchy** (all Textual widgets):
- `DiffView` (main widget, `VerticalGroup`) — owns the diff state and renders either split or unified layout via `compose_split()` / `compose_unified()`. Uses Textual's `reactive` attributes with `recompose=True` to re-layout on mode change.
- `DiffScrollContainer` (`HorizontalGroup`) — syncs horizontal scroll between left/right panels in split view.
- `LineContent` (`Visual`) — renders a single diff line with syntax highlighting and character-level diff marks.
- `LineAnnotations` — shows line numbers and optional +/- markers.
- `DiffCode` (`Static`) — container for code lines, supports text selection.
- `Ellipsis` — collapsed section indicator (⋮).

**Diff computation**: Uses `difflib.SequenceMatcher` for line-level diffs, then character-level diffs on changed lines. Expensive computation is offloaded via `prepare()` (runs in thread pool). Results are lazily cached via properties (`grouped_opcodes`, `highlighted_code_lines`).

**Syntax highlighting**: Uses Textual's `highlight` module, auto-detecting language from file path.

## Testing

- `tests/test_diff_view.py` — unit tests (fill_lists, counting, opcodes, tab expansion, loading, mounting)
- `tests/test_snapshots.py` — visual regression tests via `pytest-textual-snapshot`
- CI runs on Linux/Windows/macOS across Python 3.11–3.14
