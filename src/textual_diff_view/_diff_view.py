from __future__ import annotations


import asyncio
import difflib
from itertools import starmap
from math import ceil
from os import PathLike
from pathlib import Path
from typing import Iterable, Literal, Mapping, TypeAlias, TypeVar

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

Annotation: TypeAlias = Literal["+", "-", "/", " "]


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
    """A visual to show a diff line."""

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

    def render_strips(
        self, width: int, height: int | None, style: Style, options: RenderOptions
    ) -> list[Strip]:
        strips: list[Strip] = []
        y = 0
        selection = options.selection
        selection_style = options.selection_style or Style.null()

        annotations: list[Content] = []
        code_lines: list[Content | None] = []
        line_styles: list[str] = []

        for annotate, continution, content, color, code_length in zip(
            self.annotations,
            self.continuations,
            self.code_lines,
            self.line_styles,
            self.code_lengths,
        ):

            if content is None:
                annotations.append(annotate)
                code_lines.append(None)
                line_styles.append(color)
                continue

            fold_width = width - annotate.cell_length
            folded_lines = content.fold(fold_width)
            line_count = ceil(code_length / fold_width)
            if line_count > len(folded_lines):
                folded_lines.extend([Content()] * (line_count - len(folded_lines)))
            if len(folded_lines) == 1:
                annotations.append(annotate)
            else:
                # TODO
                annotations.append(annotate)
                annotations.extend([continution] * (len(folded_lines) - 1))

            code_lines.extend(folded_lines)
            line_styles.extend([color] * len(folded_lines))

        for y, (annotate, line, color) in enumerate(
            zip(annotations, code_lines, line_styles)
        ):
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
                    line = line.pad_right(
                        width - line.cell_length - annotate.cell_length
                    )

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

            strips.append(
                Strip(
                    [*annotate.render_segments(style), *segments],
                    line.cell_length + annotate.cell_length,
                )
            )
        return strips

    def get_optimal_width(self, rules: RulesMap, container_width: int) -> int:
        return container_width

    def get_minimal_width(self, rules: RulesMap) -> int:
        return 1

    def get_height(self, rules: RulesMap, width: int) -> int:
        height = 0
        for annotate, content in zip(self.annotations, self.code_lines):
            fold_width = max(0, width - annotate.cell_length)
            if content is None:
                height += 1
            else:
                height += len(content.fold(fold_width))
        return height


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
        if isinstance(visual, LineContent):
            text = "\n".join(
                "" if line is None else line.plain for line in visual.code_lines
            )
        else:
            return None
        return selection.extract(text), "\n"


T = TypeVar("T")


def fill_lists(list_a: list[T], list_b: list[T], fill_value: T) -> None:
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
    annotations: reactive[bool] = reactive(False, recompose=True)
    """Show annotations?"""
    auto_split: var[bool] = var(False)
    """Automaticallly enable split view if there is enough space?"""
    wrap: reactive[bool] = reactive(False, recompose=True)
    """Wrap long lines (rather than horizontal scroll)."""

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
    ANNOTATION_STYLES = {
        "+": "$text-success 95%",
        "-": "$text-error 95%",
        " ": "",
    }
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
        split: bool = True,
        annotations: bool = False,
        auto_split: bool = False,
        wrap: bool = False,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ):
        """Initialize diff view.

        Args:
            path_original: Path to original code.
            path_modified: Path to modified code.
            code_original: Original code.
            code_modified: Modified code.
            split: Enable split view?
            annotations: Enable annotations ("+" and  "-")?
            auto_split: Automatically enable split view if it fits?
            wrap: Wrap code (rather than horizontal scroll)?
            name: Textual CSS name.
            id: Textual CSS id.
            classes: Textual CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.set_reactive(DiffView.path_original, path_original)
        self.set_reactive(DiffView.path_modified, path_modified)
        self.set_reactive(DiffView.code_original, code_original.expandtabs())
        self.set_reactive(DiffView.code_modified, code_modified.expandtabs())

        self.set_reactive(DiffView.split, split)
        self.set_reactive(DiffView.annotations, annotations)
        self.set_reactive(DiffView.auto_split, auto_split)
        self.set_reactive(DiffView.wrap, wrap)

        self._grouped_opcodes: list[list[tuple[str, int, int, int, int]]] | None = None
        self._highlighted_code_lines: tuple[list[Content], list[Content]] | None = None

    @classmethod
    async def load(
        cls,
        path_original: str | PathLike,
        path_modified: str | PathLike,
        *,
        split: bool = True,
        annotations: bool = False,
        auto_split: bool = False,
        wrap: bool = False,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> DiffView:
        """Load two files from disk.

        This is a helper for diffing two files on disk.

        Args:
            path_original: A str or Path to the original file.
            path_modified: A str or Path to the modified file.
            split: Enable split view?
            annotations: Enable annotations ("+" and  "-")?
            auto_split: Automatically enable split view if it fits?
            wrap: Wrap code (rather than horizontal scroll)?
            name: Textual CSS name.
            id: Textual CSS id.
            classes: Textual CSS classes.

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
            split=split,
            annotations=annotations,
            auto_split=auto_split,
            wrap=wrap,
            name=name,
            id=id,
            classes=classes,
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
        if self.split:
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

    async def on_resize(self, event: events.Resize) -> None:
        self._check_auto_split(event.size.width)

    async def on_mount(self) -> None:
        self._check_auto_split(self.size.width)

    def compose_unified(self) -> ComposeResult:
        """Compose unified view."""
        # Branch for wrapping
        if self.wrap:
            yield from self._compose_unified_wrap()
        else:
            yield from self._compose_unified()

    def _compose_unified(self) -> ComposeResult:
        """Compose unified view (no wrapping)."""
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

                if self.annotations:
                    yield LineAnnotations(
                        [
                            (Content(f" {annotation} "))
                            .stylize(LINE_STYLES[annotation])
                            .stylize(ANNOTATION_STYLES[annotation])
                            for annotation in annotations
                        ]
                    )
                else:
                    blank = Content.blank(1)
                    yield LineAnnotations(
                        [
                            blank.stylize(LINE_STYLES[annotation]).stylize(
                                ANNOTATION_STYLES[annotation]
                            )
                            for annotation in annotations
                        ]
                    )
                code_line_styles = [
                    LINE_STYLES[annotation] for annotation in annotations
                ]
                with DiffScrollContainer():
                    yield DiffCode(LineContent(code_lines, code_line_styles))

            if not last:
                yield Ellipsis("⋮")

    def _make_continuations(self, width: int) -> Mapping[str, Content]:
        """Make continuations (content used in gutter when a line wraps).

        Args:
            width: Width of the gutter.

        Returns:
            Mapping of annotation to content.
        """

        blank_continuation = Content.styled(f"▎{' ' * (width - 2)} ")
        add_continuation = blank_continuation.stylize(self.EDGE_STYLES["+"])
        remove_contuation = blank_continuation.stylize(self.EDGE_STYLES["-"])
        blank_continuation = blank_continuation.stylize(self.EDGE_STYLES[" "])

        if self.annotations:
            add_continuation = add_continuation.append(
                Content.styled(" ↪ ", self.LINE_STYLES["+"]).stylize(
                    self.ANNOTATION_STYLES["+"]
                )
            )
            remove_contuation = remove_contuation.append(
                Content.styled(" ↪ ", self.LINE_STYLES["-"]).stylize(
                    self.ANNOTATION_STYLES["-"]
                )
            )
            blank_continuation = blank_continuation.append(
                Content.styled(" ↪ ", self.LINE_STYLES[" "])
            ).stylize("dim")
        else:
            add_continuation = add_continuation.append(
                Content.blank(1, self.LINE_STYLES["+"])
            )
            remove_contuation = remove_contuation.append(
                Content.blank(1, self.LINE_STYLES["-"])
            )
            blank_continuation = blank_continuation.append(
                Content.blank(1, self.LINE_STYLES[" "])
            )

        continuations = {
            "+": add_continuation,
            "-": remove_contuation,
            " ": blank_continuation,
            "/": blank_continuation,
        }
        return continuations

    def _compose_unified_wrap(self) -> ComposeResult:
        """Compose unified view with wrapping."""
        lines_a, lines_b = self.highlighted_code_lines

        for last, group in loop_last(self.grouped_opcodes):
            line_numbers_a: list[int | None] = []
            line_numbers_b: list[int | None] = []
            line_annotations: list[str] = []
            code_lines: list[Content | None] = []
            for tag, i1, i2, j1, j2 in group:
                if tag == "equal":
                    for line_offset, line in enumerate(lines_a[i1:i2], 1):
                        line_annotations.append(" ")
                        line_numbers_a.append(i1 + line_offset)
                        line_numbers_b.append(j1 + line_offset)
                        code_lines.append(line)
                    continue
                if tag in {"delete", "replace"}:
                    for line_offset, line in enumerate(lines_a[i1:i2], 1):
                        line_annotations.append("-")
                        line_numbers_a.append(i1 + line_offset)
                        line_numbers_b.append(None)
                        code_lines.append(line)
                if tag in {"insert", "replace"}:
                    for line_offset, line in enumerate(lines_b[j1:j2], 1):
                        line_annotations.append("+")
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
                annotations: list[list[Content]] = []

                for line_no_a, line_no_b, annotation in zip(
                    line_numbers_a, line_numbers_b, line_annotations
                ):
                    annotations_line = []
                    annotations.append(annotations_line)
                    annotations_line.append(
                        (
                            Content(f"▎{' ' * line_number_width} ")
                            if line_no_a is None
                            else Content(f"▎{line_no_a:>{line_number_width}} ")
                        )
                        .stylize(NUMBER_STYLES[annotation], 1)
                        .stylize(EDGE_STYLES[annotation], 0, 1)
                    )
                    annotations_line.append(
                        (
                            Content(f" {' ' * line_number_width} ")
                            if line_no_b is None
                            else Content(f" {line_no_b:>{line_number_width}} ")
                        ).stylize(NUMBER_STYLES[annotation])
                    )

                    annotations_line.append(
                        (Content(f" {annotation} " if self.annotations else " "))
                        .stylize(LINE_STYLES[annotation])
                        .stylize(ANNOTATION_STYLES[annotation])
                    )

                annotation_prefixes = [
                    Content("").join(annotate) for annotate in annotations
                ]

                continuations = self._make_continuations(line_number_width * 2 + 4)
                code_line_styles = [
                    LINE_STYLES[annotation] for annotation in line_annotations
                ]

                with DiffScrollContainer():
                    yield DiffCode(
                        FoldedLineContent(
                            annotation_prefixes,
                            [
                                (continuations[annotate])
                                for annotate in line_annotations
                            ],
                            code_lines,
                            code_line_styles,
                        )
                    )

            if not last:
                yield Ellipsis("⋮")

    def compose_split(self) -> ComposeResult:
        """Compose split view"""
        # Branch for wrapping
        if self.wrap:
            yield from self._compose_split_wrap()
        else:
            yield from self._compose_split()

    def _compose_split(self) -> ComposeResult:
        """Compose the split view (no wrapping)."""
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
            if not self.annotations:
                return Content(" ").stylize(self.LINE_STYLES[annotation])
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

    def _compose_split_wrap(self) -> ComposeResult:
        """Compse split view with wrapping."""
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
            if not self.annotations:
                return (
                    Content.blank(1)
                    .stylize(self.LINE_STYLES[annotation])
                    .stylize(self.ANNOTATION_STYLES.get(annotation, ""))
                )
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

            code_lengths = [
                max(
                    0 if line_a is None else line_a.cell_length,
                    0 if line_b is None else line_b.cell_length,
                )
                for line_a, line_b in zip(code_lines_a, code_lines_b)
            ]

            with containers.HorizontalGroup(classes="diff-group"):
                annotations = [
                    Content.assemble(
                        format_number(line_number, annotation),
                        make_annotation(annotation, "-"),
                    )
                    for line_number, annotation in zip(line_numbers_a, annotations_a)
                ]
                continuations = self._make_continuations(line_number_width + 2)
                code_line_styles = [
                    self.LINE_STYLES[annotation] for annotation in annotations_a
                ]

                # Before code
                with DiffScrollContainer():
                    yield DiffCode(
                        FoldedLineContent(
                            annotations,
                            [(continuations[annotate]) for annotate in annotations_a],
                            code_lines_a,
                            code_line_styles,
                            code_lengths=code_lengths,
                        )
                    )

                annotations = [
                    Content.assemble(
                        format_number(line_number, annotation),
                        make_annotation(annotation, "+"),
                    )
                    for line_number, annotation in zip(line_numbers_b, annotations_b)
                ]

                code_line_styles = [
                    self.LINE_STYLES[annotation] for annotation in annotations_b
                ]

                # Before code
                with DiffScrollContainer():
                    yield DiffCode(
                        FoldedLineContent(
                            annotations,
                            [(continuations[annotate]) for annotate in annotations_b],
                            code_lines_b,
                            code_line_styles,
                            code_lengths=code_lengths,
                        )
                    )

            if not last:
                with containers.HorizontalGroup():
                    yield Ellipsis("⋮")
                    yield Ellipsis("⋮")
