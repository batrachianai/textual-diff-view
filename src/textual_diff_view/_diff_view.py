from __future__ import annotations


import asyncio
import difflib
from itertools import starmap
from math import ceil
from os import PathLike
from pathlib import Path
from typing import Iterable, Literal

from rich.segment import Segment
from rich.style import Style as RichStyle

from textual.app import ComposeResult
from textual.content import Content, Span
from textual.geometry import Size
from textual import highlight
from textual import events

from textual.css.styles import RulesMap
from textual.selection import Selection
from textual.strip import Strip
from textual.style import Style
from textual.reactive import reactive, var
from textual.visual import Visual, RenderOptions
from textual.widget import Widget
from textual.widgets import Static
from textual import containers

from textual._loop import loop_last

type Annotation = Literal["+", "-", "/", " "]


class LoadError(Exception):
    """Raised when DiffView.load fails in loading code."""


class Ellipsis(Static):
    """A non selectable Static for the ellipsis."""

    ALLOW_SELECT = False


class DiffScrollContainer(containers.HorizontalGroup):
    """A horizontally scrolling container, that also scrolls is sibling."""

    scroll_link: var[Widget | None] = var(None)
    DEFAULT_CSS = """
    DiffScrollContainer {
        overflow: scroll hidden;
        scrollbar-size: 0 0;
        height: auto;        
    }
    """

    def watch_scroll_x(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_x(old_value, new_value)
        if self.scroll_link:
            self.scroll_link.scroll_x = new_value


class LineContent(Visual):
    """A visual to show a diff line."""

    def __init__(
        self,
        code_lines: list[Content | None],
        line_styles: list[str],
        width: int | None = None,
    ) -> None:
        self.code_lines = code_lines
        self.line_styles = line_styles
        self._width = width

    def render_strips(
        self, width: int, height: int | None, style: Style, options: RenderOptions
    ) -> list[Strip]:
        strips: list[Strip] = []
        y = 0
        selection = options.selection
        selection_style = options.selection_style or Style.null()
        for y, (line, color) in enumerate(zip(self.code_lines, self.line_styles)):
            if line is None:
                line = Content.styled("╲" * width, "$foreground 15%")
            else:
                if selection is not None:
                    if span := selection.get_span(y):
                        start, end = span
                        if end == -1:
                            end = len(line)
                        line = line.stylize(selection_style, start, end)
                if line.cell_length < width:
                    line = line.pad_right(width - line.cell_length)

            line = line.stylize_before(color).stylize_before(style)
            x = 0
            meta = {"offset": (x, y)}
            segments = []
            for text, rich_style, _ in line.render_segments():
                if rich_style is not None:
                    meta["offset"] = (x, y)
                    segments.append(
                        Segment(text, rich_style + RichStyle.from_meta(meta))
                    )
                else:
                    segments.append(Segment(text, rich_style))
                x += len(text)

            strips.append(Strip(segments, line.cell_length))
        return strips

    def get_optimal_width(self, rules: RulesMap, container_width: int) -> int:
        if self._width is not None:
            return self._width
        return max(line.cell_length for line in self.code_lines if line is not None)

    def get_minimal_width(self, rules: RulesMap) -> int:
        return 1

    def get_height(self, rules: RulesMap, width: int) -> int:
        return len(self.line_styles)


class FoldedLineContent(Visual):
    """A visual that folds (wraps) code lines at render time, with inline gutter."""

    def __init__(
        self,
        annotations: list[Content],
        continuations: list[Content],
        code_lines: list[Content | None],
        line_styles: list[str],
        code_lengths: list[int] | None = None,
    ) -> None:
        self.annotations = annotations
        self.continuations = continuations
        self.code_lines = code_lines
        self.line_styles = line_styles
        self.code_lengths = (
            [0 if line is None else line.cell_length for line in code_lines]
            if code_lengths is None
            else code_lengths
        )

    @property
    def _gutter_width(self) -> int:
        if not self.annotations:
            return 0
        return self.annotations[0].cell_length

    def _fold_width(self, width: int) -> int:
        return max(2, width - self._gutter_width)

    def _line_count(self, code_length: int, fold_width: int) -> int:
        if code_length <= fold_width:
            return 1
        return ceil(code_length / fold_width)

    def get_height(self, rules: RulesMap, width: int) -> int:
        fold_width = self._fold_width(width)
        return sum(
            self._line_count(cl, fold_width) for cl in self.code_lengths
        )

    def get_optimal_width(self, rules: RulesMap, container_width: int) -> int:
        return container_width

    def get_minimal_width(self, rules: RulesMap) -> int:
        return self._gutter_width + 2

    def render_strips(
        self, width: int, height: int | None, style: Style, options: RenderOptions
    ) -> list[Strip]:
        strips: list[Strip] = []
        fold_width = self._fold_width(width)
        y = 0
        selection = options.selection
        selection_style = options.selection_style or Style.null()
        visual_code_lines: list[str] = []

        for annotate, cont, content, color, code_length in zip(
            self.annotations,
            self.continuations,
            self.code_lines,
            self.line_styles,
            self.code_lengths,
        ):
            line_count = self._line_count(code_length, fold_width)

            if content is None:
                hatch = Content.styled("╲" * width, "$foreground 15%")
                hatch = hatch.stylize_before(style)
                for _ in range(line_count):
                    meta: dict[str, object] = {"offset": (0, y)}
                    segments = [
                        Segment(text, rich_style + RichStyle.from_meta(meta) if rich_style else rich_style)
                        for text, rich_style, _ in hatch.render_segments()
                    ]
                    strips.append(Strip(segments, width))
                    visual_code_lines.append("")
                    y += 1
                continue

            if content.cell_length <= fold_width:
                folded: list[Content] = [content]
            else:
                folded = content.fold(fold_width)

            actual_count = len(folded)
            while len(folded) < line_count:
                folded.append(Content(""))

            for i, part in enumerate(folded):
                if i == 0:
                    ann = annotate
                elif i < actual_count:
                    ann = cont
                else:
                    ann = cont

                visual_code_lines.append(part.plain)
                ann_width = ann.cell_length
                code_w = width - ann_width

                if selection is not None:
                    if span := selection.get_span(y):
                        start, end = span
                        start = max(0, start - ann_width)
                        if end == -1:
                            end = len(part)
                        else:
                            end = max(0, end - ann_width)
                        if end > start:
                            part = part.stylize(selection_style, start, end)

                if part.cell_length < code_w:
                    part = part.pad_right(code_w - part.cell_length)

                part = part.stylize_before(color)
                combined = Content("").join([ann, part])
                combined = combined.stylize_before(style)

                segments = []
                x = 0
                meta = {"offset": (x, y)}
                for text, rich_style, _ in combined.render_segments():
                    if rich_style is not None:
                        meta["offset"] = (x, y)
                        segments.append(
                            Segment(text, rich_style + RichStyle.from_meta(meta))
                        )
                    else:
                        segments.append(Segment(text, rich_style))
                    x += len(text)
                strips.append(Strip(segments, combined.cell_length))
                y += 1

        self._visual_code_lines = visual_code_lines
        return strips


class LineAnnotations(Widget):
    """A vertical strip next to the code, containing line numbers or symbols."""

    DEFAULT_CSS = """
    LineAnnotations {
        width: auto;
        height: auto;                
    }
    """
    numbers: reactive[list[Content]] = reactive(list)

    def __init__(
        self,
        numbers: Iterable[Content],
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ):
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.numbers = list(numbers)

    @property
    def total_width(self) -> int:
        return self.number_width

    def get_content_width(self, container: Size, viewport: Size) -> int:
        return self.total_width

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        return len(self.numbers)

    @property
    def number_width(self) -> int:
        return max(number.cell_length for number in self.numbers) if self.numbers else 0

    def render_line(self, y: int) -> Strip:
        width = self.total_width
        visual_style = self.visual_style
        rich_style = visual_style.rich_style
        try:
            number = self.numbers[y]
        except IndexError:
            number = Content.empty()

        strip = Strip(
            number.render_segments(visual_style), cell_length=number.cell_length
        )
        strip = strip.adjust_cell_length(width, rich_style)
        return strip


class DiffCode(Static):
    """Container for the code."""

    DEFAULT_CSS = """
    DiffCode {
        width: auto;        
        height: auto;
        min-width: 1fr;
    }
    """
    ALLOW_SELECT = True

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        visual = self._render()
        if isinstance(visual, FoldedLineContent):
            text = "\n".join(
                getattr(visual, "_visual_code_lines", [])
            )
        elif isinstance(visual, LineContent):
            text = "\n".join(
                "" if line is None else line.plain for line in visual.code_lines
            )
        else:
            return None
        return selection.extract(text), "\n"


def fill_lists[T](list_a: list[T], list_b: list[T], fill_value: T) -> None:
    """Make two lists the same size by extending the smaller with a fill value.

    Args:
        list_a: The first list.
        list_b: The second list.
        fill_value: Value used to extend a list.

    """
    a_length = len(list_a)
    b_length = len(list_b)
    if a_length != b_length:
        if a_length > b_length:
            list_b.extend([fill_value] * (a_length - b_length))
        elif b_length > a_length:
            list_a.extend([fill_value] * (b_length - a_length))


class DiffView(containers.VerticalGroup):
    """A formatted diff in unified or split format."""

    path_original: reactive[str] = reactive("")
    """Path for the original code."""
    path_modified: reactive[str] = reactive("")
    """Path for the modified code."""
    code_original: reactive[str] = reactive("")
    """The original code."""
    code_modified: reactive[str] = reactive("")
    """The modified code."""

    split: reactive[bool] = reactive(True, recompose=True)
    """Enable split view?"""
    annotations: var[bool] = var(False, toggle_class="-with-annotations")
    """Show annotations?"""
    auto_split: var[bool] = var(False)
    """Automaticallly enable split view if there is enough space?"""
    wrap: reactive[bool] = reactive(False, recompose=True)
    """Wrap long lines instead of horizontal scrolling?"""

    WRAP_SYMBOL = "↪"
    """Symbol shown in the annotation column for wrapped continuation lines."""

    DEFAULT_CSS = """
    DiffView {
        width: 1fr;
        height: auto;
        .diff-group {
            height: auto;
            background: $foreground 4%;            
        }                
        .annotations { width: 1; }
        &.-with-annotations {
            .annotations { width: auto; }
        }
        .title {            
            border-bottom: dashed $foreground 20%;
        }
        Ellipsis {
            text-align: center;
            width: 1fr;
            color: $text-primary;
            text-style:bold;
            offset-x: -1;
        }
    }
    """

    NUMBER_STYLES = {
        "+": "$text-success 80% on $success 20%",
        "-": "$text-error 80% on $error 20%",
        " ": "$foreground 30% on $foreground 3%",
    }
    """Line number styles."""
    ANNOTATION_STYLES = {"+": "$text-success", "-": "$text-error", " ": ""}
    """Annotation styles (+ or -)."""
    LINE_STYLES = {
        "+": "on $success 10%",
        "-": "on $error 10%",
        " ": "",
        "/": "",
    }
    """Base style for lines."""
    EDGE_STYLES = {
        "+": "$text-success 30% on $success 20%",
        "-": "$text-error 30% on $error 20%",
        " ": "$foreground 10% on $foreground 3%",
    }
    """Style for edge of numbers,"""

    def __init__(
        self,
        path_original: str,
        path_modified: str,
        code_original: str,
        code_modified: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ):
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.set_reactive(DiffView.path_original, path_original)
        self.set_reactive(DiffView.path_modified, path_modified)
        self.set_reactive(DiffView.code_original, code_original.expandtabs())
        self.set_reactive(DiffView.code_modified, code_modified.expandtabs())

        self._grouped_opcodes: list[list[tuple[str, int, int, int, int]]] | None = None
        self._highlighted_code_lines: tuple[list[Content], list[Content]] | None = None

    @classmethod
    async def load(
        cls, path_original: str | PathLike, path_modified: str | PathLike
    ) -> DiffView:
        """Load two files from disk.

        This is a helper for diffing two files on disk.

        Args:
            path_original: A str or Path to the original file.
            path_modified: A str or Path to the modified file.

        Raises:
            OSError: If the file could not be loaded.

        Returns:
            A DiffView widget instance.
        """
        original = Path(path_original)
        modified = Path(path_modified)

        def read(path: Path) -> str:
            """Read from a path.

            Args:
                path: Path to a text file.

            Returns:
                The contents of `path`.
            """
            try:
                return path.read_text("utf-8")
            except OSError as error:
                raise LoadError(f"Unabled to load {path!s}; {error}")

        original_code = await asyncio.to_thread(read, original)
        modified_code = await asyncio.to_thread(read, modified)

        diff_view = DiffView(
            str(original),
            str(modified),
            original_code,
            modified_code,
        )

        await diff_view.prepare()

        return diff_view

    async def prepare(self) -> None:
        """Do CPU work in a thread.

        Call this method prior to composing or mounting to ensure lazy calculated
        data structures run in a thread. Otherwise the work will be done in the async
        loop, potentially causing a brief freeze.

        """

        def prepare() -> None:
            """Call properties which will lazily update data structures."""
            self.grouped_opcodes
            self.highlighted_code_lines

        await asyncio.to_thread(prepare)

    @property
    def grouped_opcodes(self) -> list[list[tuple[str, int, int, int, int]]]:
        if self._grouped_opcodes is None:
            text_lines_a = self.code_original.splitlines()
            text_lines_b = self.code_modified.splitlines()
            sequence_matcher = difflib.SequenceMatcher(
                lambda character: character in {" ", "\t"},
                text_lines_a,
                text_lines_b,
                autojunk=True,
            )
            self._grouped_opcodes = list(sequence_matcher.get_grouped_opcodes())

        return self._grouped_opcodes

    @property
    def counts(self) -> tuple[int, int]:
        """Additions and removals."""
        additions = 0
        removals = 0
        for group in self.grouped_opcodes:
            for tag, i1, i2, j1, j2 in group:
                if tag == "delete":
                    removals += i2 - i1
                elif tag == "replace":
                    additions += j2 - j1
                    removals += i2 - i1
                elif tag == "insert":
                    additions += j2 - j1
        return additions, removals

    @classmethod
    def _highlight_diff_lines(
        cls, lines_a: list[Content], lines_b: list[Content]
    ) -> tuple[list[Content], list[Content]]:
        """Diff two groups of lines.

        Args:
            lines_a: Lines before.
            lines_b: Lines after

        Returns:
            A pair of highlighted lists of lines.
        """
        code_a = Content("\n").join(content for content in lines_a)
        code_b = Content("\n").join(content for content in lines_b)
        sequence_matcher = difflib.SequenceMatcher(
            lambda character: character in {" ", "\t"},
            code_a.plain,
            code_b.plain,
            autojunk=True,
        )
        spans_a: list[Span] = []
        spans_b: list[Span] = []
        for tag, i1, i2, j1, j2 in sequence_matcher.get_opcodes():
            if tag in {"delete", "replace"}:
                spans_a.append(Span(i1, i2, "on $error 30%"))
            if tag in {"insert", "replace"}:
                spans_b.append(Span(j1, j2, "on $success 30%"))
        diffed_lines_a = code_a.add_spans(spans_a).split("\n")
        diffed_lines_b = code_b.add_spans(spans_b).split("\n")
        return diffed_lines_a, diffed_lines_b

    @property
    def highlighted_code_lines(self) -> tuple[list[Content], list[Content]]:
        """Get syntax highlighted code for both files, as a list of lines.

        Returns:
            A pair of line lists for `code_before` and `code_after`
        """

        if self._highlighted_code_lines is None:
            language1 = highlight.guess_language(self.code_original, self.path_original)
            language2 = highlight.guess_language(self.code_modified, self.path_modified)
            text_lines_a = self.code_original.splitlines()
            text_lines_b = self.code_modified.splitlines()

            code_a = highlight.highlight(
                "\n".join(text_lines_a), language=language1, path=self.path_original
            )
            code_b = highlight.highlight(
                "\n".join(text_lines_b), language=language2, path=self.path_modified
            )

            lines_a = code_a.split("\n")
            lines_b = code_b.split("\n")

            if self.code_original:
                for group in self.grouped_opcodes:
                    for tag, i1, i2, j1, j2 in group:
                        # Show character level diff only when there is the same number of lines
                        # Otherwise you get noisy diffs that don't make a great deal of sense
                        if tag == "replace" and (j2 - j1) == (i2 - i1):
                            diff_lines_a, diff_lines_b = self._highlight_diff_lines(
                                lines_a[i1:i2], lines_b[j1:j2]
                            )
                            lines_a[i1:i2] = diff_lines_a
                            lines_b[j1:j2] = diff_lines_b

            self._highlighted_code_lines = (lines_a, lines_b)

        return self._highlighted_code_lines

    def get_title(self) -> Content:
        """Get a title for the diff view.

        May be implemented in as subclass to provide a custom title.

        Returns:
            A Content instance.
        """
        additions, removals = self.counts
        title = Content.from_markup(
            "📄 [dim]$path[/dim] ([$text-success][b]+$additions[/b][/], [$text-error][b]-$removals[/b][/])",
            path=self.path_modified,
            additions=additions,
            removals=removals,
            additions_label="addition" if additions == 1 else "additions",
            removals_label="removals" if removals == 1 else "removals",
        ).stylize_before("$text")
        return title

    def compose(self) -> ComposeResult:
        """Compose either split or unified view."""

        yield Static(self.get_title(), classes="title")
        if self.wrap:
            if self.split:
                yield from self.compose_split_wrap()
            else:
                yield from self.compose_unified_wrap()
        elif self.split:
            yield from self.compose_split()
        else:
            yield from self.compose_unified()

    def _check_auto_split(self, width: int):
        """Check if the view can split can split without obscuring any code."""
        if self.auto_split:
            lines_a, lines_b = self.highlighted_code_lines
            split_width = max([line.cell_length for line in (lines_a + lines_b)]) * 2
            split_width += 4 + 2 * (
                max(
                    [
                        len(str(len(lines_a))),
                        len(str(len(lines_b))),
                    ]
                )
            )
            split_width += 3 * 2 if self.annotations else 2
            self.split = width >= split_width

    async def watch_annotations(self) -> None:
        if self.wrap:
            await self.recompose()

    def on_resize(self, event: events.Resize) -> None:
        self._check_auto_split(event.size.width)

    def on_mount(self) -> None:
        self._check_auto_split(self.size.width)

    def compose_unified(self) -> ComposeResult:
        lines_a, lines_b = self.highlighted_code_lines

        for last, group in loop_last(self.grouped_opcodes):
            line_numbers_a: list[int | None] = []
            line_numbers_b: list[int | None] = []
            annotations: list[str] = []
            code_lines: list[Content | None] = []
            for tag, i1, i2, j1, j2 in group:
                if tag == "equal":
                    for line_offset, line in enumerate(lines_a[i1:i2], 1):
                        annotations.append(" ")
                        line_numbers_a.append(i1 + line_offset)
                        line_numbers_b.append(j1 + line_offset)
                        code_lines.append(line)
                    continue
                if tag in {"delete", "replace"}:
                    for line_offset, line in enumerate(lines_a[i1:i2], 1):
                        annotations.append("-")
                        line_numbers_a.append(i1 + line_offset)
                        line_numbers_b.append(None)
                        code_lines.append(line)
                if tag in {"insert", "replace"}:
                    for line_offset, line in enumerate(lines_b[j1:j2], 1):
                        annotations.append("+")
                        line_numbers_a.append(None)
                        line_numbers_b.append(j1 + line_offset)
                        code_lines.append(line)

            NUMBER_STYLES = self.NUMBER_STYLES
            LINE_STYLES = self.LINE_STYLES
            EDGE_STYLES = self.EDGE_STYLES
            ANNOTATION_STYLES = self.ANNOTATION_STYLES

            line_number_width = max(
                len("" if line_no is None else str(line_no))
                for line_no in (line_numbers_a + line_numbers_b)
            )

            with containers.HorizontalGroup(classes="diff-group"):
                yield LineAnnotations(
                    [
                        (
                            Content(f"▎{' ' * line_number_width} ")
                            if line_no is None
                            else Content(f"▎{line_no:>{line_number_width}} ")
                        )
                        .stylize(NUMBER_STYLES[annotation], 1)
                        .stylize(EDGE_STYLES[annotation], 0, 1)
                        for line_no, annotation in zip(line_numbers_a, annotations)
                    ]
                )

                yield LineAnnotations(
                    [
                        (
                            Content(f" {' ' * line_number_width} ")
                            if line_no is None
                            else Content(f" {line_no:>{line_number_width}} ")
                        ).stylize(NUMBER_STYLES[annotation])
                        for line_no, annotation in zip(line_numbers_b, annotations)
                    ]
                )

                yield LineAnnotations(
                    [
                        (Content(f" {annotation} "))
                        .stylize(LINE_STYLES[annotation])
                        .stylize(ANNOTATION_STYLES[annotation])
                        for annotation in annotations
                    ],
                    classes="annotations",
                )
                code_line_styles = [
                    LINE_STYLES[annotation] for annotation in annotations
                ]
                with DiffScrollContainer():
                    yield DiffCode(LineContent(code_lines, code_line_styles))

            if not last:
                yield Ellipsis("⋮")

    def compose_unified_wrap(self) -> ComposeResult:
        lines_a, lines_b = self.highlighted_code_lines
        show_annotations = self.annotations

        NUMBER_STYLES = self.NUMBER_STYLES
        LINE_STYLES = self.LINE_STYLES
        EDGE_STYLES = self.EDGE_STYLES
        ANNOTATION_STYLES = self.ANNOTATION_STYLES

        for last, group in loop_last(self.grouped_opcodes):
            line_numbers_a: list[int | None] = []
            line_numbers_b: list[int | None] = []
            ann_types: list[str] = []
            code_lines: list[Content | None] = []
            for tag, i1, i2, j1, j2 in group:
                if tag == "equal":
                    for line_offset, line in enumerate(lines_a[i1:i2], 1):
                        ann_types.append(" ")
                        line_numbers_a.append(i1 + line_offset)
                        line_numbers_b.append(j1 + line_offset)
                        code_lines.append(line)
                    continue
                if tag in {"delete", "replace"}:
                    for line_offset, line in enumerate(lines_a[i1:i2], 1):
                        ann_types.append("-")
                        line_numbers_a.append(i1 + line_offset)
                        line_numbers_b.append(None)
                        code_lines.append(line)
                if tag in {"insert", "replace"}:
                    for line_offset, line in enumerate(lines_b[j1:j2], 1):
                        ann_types.append("+")
                        line_numbers_a.append(None)
                        line_numbers_b.append(j1 + line_offset)
                        code_lines.append(line)

            numw = max(
                len("" if n is None else str(n))
                for n in (line_numbers_a + line_numbers_b)
            )

            gutter_annotations: list[Content] = []
            gutter_continuations: list[Content] = []

            for num_a, num_b, ann in zip(line_numbers_a, line_numbers_b, ann_types):
                ga = (
                    Content(f"▎{' ' * numw} ")
                    if num_a is None
                    else Content(f"▎{num_a:>{numw}} ")
                ).stylize(NUMBER_STYLES[ann], 1).stylize(EDGE_STYLES[ann], 0, 1)

                gb = (
                    Content(f" {' ' * numw} ")
                    if num_b is None
                    else Content(f" {num_b:>{numw}} ")
                ).stylize(NUMBER_STYLES[ann])

                if show_annotations:
                    ac = (Content(f" {ann} ")
                        .stylize(LINE_STYLES[ann])
                        .stylize(ANNOTATION_STYLES[ann]))
                else:
                    ac = Content(" ").stylize(LINE_STYLES[ann])
                gutter_annotations.append(Content("").join([ga, gb, ac]))

                ga_c = (Content(f"▎{' ' * numw} ")
                    .stylize(NUMBER_STYLES[ann], 1)
                    .stylize(EDGE_STYLES[ann], 0, 1))
                gb_c = Content(f" {' ' * numw} ").stylize(NUMBER_STYLES[ann])
                if show_annotations:
                    ac_c = (Content(f" {self.WRAP_SYMBOL} ")
                        .stylize(LINE_STYLES[ann])
                        .stylize(ANNOTATION_STYLES[ann]))
                else:
                    ac_c = Content(" ").stylize(LINE_STYLES[ann])
                gutter_continuations.append(Content("").join([ga_c, gb_c, ac_c]))

            line_styles = [LINE_STYLES[ann] for ann in ann_types]

            with containers.HorizontalGroup(classes="diff-group"):
                yield DiffCode(FoldedLineContent(
                    gutter_annotations, gutter_continuations,
                    code_lines, line_styles,
                ))

            if not last:
                yield Ellipsis("⋮")

    def compose_split_wrap(self) -> ComposeResult:
        lines_a, lines_b = self.highlighted_code_lines
        show_annotations = self.annotations

        NUMBER_STYLES = self.NUMBER_STYLES
        LINE_STYLES = self.LINE_STYLES
        EDGE_STYLES = self.EDGE_STYLES
        ANNOTATION_STYLES = self.ANNOTATION_STYLES

        for last, group in loop_last(self.grouped_opcodes):
            line_numbers_a: list[int | None] = []
            line_numbers_b: list[int | None] = []
            annotations_a: list[Annotation] = []
            annotations_b: list[Annotation] = []
            code_lines_a: list[Content | None] = []
            code_lines_b: list[Content | None] = []
            for tag, i1, i2, j1, j2 in group:
                if tag == "equal":
                    for line_offset, line in enumerate(lines_a[i1:i2], 1):
                        annotations_a.append(" ")
                        annotations_b.append(" ")
                        line_numbers_a.append(i1 + line_offset)
                        line_numbers_b.append(j1 + line_offset)
                        code_lines_a.append(line)
                        code_lines_b.append(line)
                else:
                    if tag in {"delete", "replace"}:
                        for line_number, line in enumerate(lines_a[i1:i2], i1 + 1):
                            annotations_a.append("-")
                            line_numbers_a.append(line_number)
                            code_lines_a.append(line)
                    if tag in {"insert", "replace"}:
                        for line_number, line in enumerate(lines_b[j1:j2], j1 + 1):
                            annotations_b.append("+")
                            line_numbers_b.append(line_number)
                            code_lines_b.append(line)
                    fill_lists(code_lines_a, code_lines_b, None)
                    fill_lists(annotations_a, annotations_b, "/")
                    fill_lists(line_numbers_a, line_numbers_b, None)

            if line_numbers_a or line_numbers_b:
                numw = max(
                    0 if n is None else len(str(n))
                    for n in (line_numbers_a + line_numbers_b)
                )
            else:
                numw = 1

            ann_col_width = 3 if show_annotations else 1
            full_gutter_width = 2 + numw + ann_col_width

            def build_side(
                line_numbers: list[int | None],
                ann_list: list[Annotation],
                highlight_ann: Literal["+", "-"],
            ) -> tuple[list[Content], list[Content]]:
                gutter_anns: list[Content] = []
                gutter_conts: list[Content] = []
                for line_no, ann in zip(line_numbers, ann_list):
                    if ann == "/":
                        hatch = Content.styled(
                            "╲" * full_gutter_width, "$foreground 15%"
                        )
                        gutter_anns.append(hatch)
                        gutter_conts.append(hatch)
                        continue

                    if line_no is None:
                        g = (Content(f"▎{' ' * numw} ")
                            .stylize(NUMBER_STYLES[ann], 1)
                            .stylize(EDGE_STYLES[ann], 0, 1))
                    else:
                        g = (Content(f"▎{line_no:>{numw}} ")
                            .stylize(NUMBER_STYLES[ann], 1)
                            .stylize(EDGE_STYLES[ann], 0, 1))

                    if show_annotations and ann == highlight_ann:
                        ac = (Content(f" {ann} ")
                            .stylize(LINE_STYLES[ann])
                            .stylize(ANNOTATION_STYLES.get(ann, "")))
                    elif show_annotations:
                        ac = Content("   ")
                    else:
                        ac = Content(" ").stylize(LINE_STYLES.get(ann, ""))
                    gutter_anns.append(Content("").join([g, ac]))

                    g_c = (Content(f"▎{' ' * numw} ")
                        .stylize(NUMBER_STYLES[ann], 1)
                        .stylize(EDGE_STYLES[ann], 0, 1))
                    if show_annotations:
                        ac_c = (Content(f" {self.WRAP_SYMBOL} ")
                            .stylize(LINE_STYLES.get(ann, ""))
                            .stylize(ANNOTATION_STYLES.get(ann, "")))
                    else:
                        ac_c = Content(" ").stylize(LINE_STYLES.get(ann, ""))
                    gutter_conts.append(Content("").join([g_c, ac_c]))

                return gutter_anns, gutter_conts

            anns_a, conts_a = build_side(
                line_numbers_a, annotations_a, "-"
            )
            anns_b, conts_b = build_side(
                line_numbers_b, annotations_b, "+"
            )

            styles_a = [LINE_STYLES[ann] for ann in annotations_a]
            styles_b = [LINE_STYLES[ann] for ann in annotations_b]

            shared_lengths = [
                max(
                    0 if a is None else a.cell_length,
                    0 if b is None else b.cell_length,
                )
                for a, b in zip(code_lines_a, code_lines_b)
            ]

            with containers.HorizontalGroup(classes="diff-group"):
                diff_code_a = DiffCode(FoldedLineContent(
                    anns_a, conts_a, code_lines_a, styles_a, shared_lengths,
                ))
                diff_code_a.styles.width = "1fr"
                yield diff_code_a

                diff_code_b = DiffCode(FoldedLineContent(
                    anns_b, conts_b, code_lines_b, styles_b, shared_lengths,
                ))
                diff_code_b.styles.width = "1fr"
                yield diff_code_b

            if not last:
                with containers.HorizontalGroup():
                    yield Ellipsis("⋮")
                    yield Ellipsis("⋮")

    def compose_split(self) -> ComposeResult:
        lines_a, lines_b = self.highlighted_code_lines

        annotation_hatch = Content.styled("╲" * 3, "$foreground 15%")
        annotation_blank = Content(" " * 3)

        def make_annotation(
            annotation: Annotation, highlight_annotation: Literal["+", "-"]
        ) -> Content:
            """Format an annotation.

            Args:
                annotation: Annotation to format.
                highlight_annotation: Annotation to highlight ('+' or '-')

            Returns:
                Content with annotation.
            """
            if annotation == highlight_annotation:
                return (
                    Content(f" {annotation} ")
                    .stylize(self.LINE_STYLES[annotation])
                    .stylize(self.ANNOTATION_STYLES.get(annotation, ""))
                )
            if annotation == "/":
                return annotation_hatch
            return annotation_blank

        for last, group in loop_last(self.grouped_opcodes):
            line_numbers_a: list[int | None] = []
            line_numbers_b: list[int | None] = []
            annotations_a: list[Annotation] = []
            annotations_b: list[Annotation] = []
            code_lines_a: list[Content | None] = []
            code_lines_b: list[Content | None] = []
            for tag, i1, i2, j1, j2 in group:
                if tag == "equal":
                    for line_offset, line in enumerate(lines_a[i1:i2], 1):
                        annotations_a.append(" ")
                        annotations_b.append(" ")
                        line_numbers_a.append(i1 + line_offset)
                        line_numbers_b.append(j1 + line_offset)
                        code_lines_a.append(line)
                        code_lines_b.append(line)
                else:
                    if tag in {"delete", "replace"}:
                        for line_number, line in enumerate(lines_a[i1:i2], i1 + 1):
                            annotations_a.append("-")
                            line_numbers_a.append(line_number)
                            code_lines_a.append(line)
                    if tag in {"insert", "replace"}:
                        for line_number, line in enumerate(lines_b[j1:j2], j1 + 1):
                            annotations_b.append("+")
                            line_numbers_b.append(line_number)
                            code_lines_b.append(line)
                    fill_lists(code_lines_a, code_lines_b, None)
                    fill_lists(annotations_a, annotations_b, "/")
                    fill_lists(line_numbers_a, line_numbers_b, None)

            if line_numbers_a or line_numbers_b:
                line_number_width = max(
                    0 if line_no is None else len(str(line_no))
                    for line_no in (line_numbers_a + line_numbers_b)
                )
            else:
                line_number_width = 1

            hatch = Content.styled("╲" * (2 + line_number_width), "$foreground 15%")

            def format_number(line_no: int | None, annotation: str) -> Content:
                """Format a line number with an annotation.

                Args:
                    line_no: Line number or `None` if there is no line here.
                    annotation: An annotation string ('+', '-', or ' ')

                Returns:
                    Content for use in the `LineAnnotations` widget.
                """
                return (
                    hatch
                    if line_no is None
                    else Content(f"▎{line_no:>{line_number_width}} ")
                    .stylize(self.NUMBER_STYLES[annotation], 1)
                    .stylize(self.EDGE_STYLES[annotation], 0, 1)
                )

            with containers.HorizontalGroup(classes="diff-group"):
                # Before line numbers
                yield LineAnnotations(
                    starmap(format_number, zip(line_numbers_a, annotations_a))
                )
                # Before annotations
                yield LineAnnotations(
                    [make_annotation(annotation, "-") for annotation in annotations_a],
                    classes="annotations",
                )

                code_line_styles = [
                    self.LINE_STYLES[annotation] for annotation in annotations_a
                ]
                line_width = max(
                    line.cell_length
                    for line in code_lines_a + code_lines_b
                    if line is not None
                )
                # Before code
                with DiffScrollContainer() as scroll_container_a:
                    yield DiffCode(
                        LineContent(code_lines_a, code_line_styles, width=line_width)
                    )

                # After line numbers
                yield LineAnnotations(
                    starmap(format_number, zip(line_numbers_b, annotations_b))
                )
                # After annotations
                yield LineAnnotations(
                    [make_annotation(annotation, "+") for annotation in annotations_b],
                    classes="annotations",
                )

                code_line_styles = [
                    self.LINE_STYLES[annotation] for annotation in annotations_b
                ]
                # After code
                with DiffScrollContainer() as scroll_container_b:
                    yield DiffCode(
                        LineContent(code_lines_b, code_line_styles, width=line_width)
                    )

                # Link scroll containers, so they scroll together
                scroll_container_a.scroll_link = scroll_container_b
                scroll_container_b.scroll_link = scroll_container_a

            if not last:
                with containers.HorizontalGroup():
                    yield Ellipsis("⋮")
                    yield Ellipsis("⋮")
