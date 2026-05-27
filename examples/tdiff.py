from rich.terminal_theme import TerminalTheme

from textual import on
from textual.app import App, ComposeResult
from textual import containers
from textual import messages
from textual.reactive import var
from textual import widgets

from textual_diff_view import DiffView, LoadError


class DiffApp(App):
    """Simple app to display a diff between two files."""

    BINDINGS = [
        ("space", "toggle('split')", "Toggle split"),
        ("a", "toggle('annotations')", "Toggle annotations"),
        ("w", "toggle('wrap')", "Toggle wrap"),
    ]

    split = var(True)
    annotations = var(True)
    wrap = var(True)

    def __init__(self, original: str, modified: str) -> None:
        self.original = original
        self.modified = modified
        self._terminal_theme: TerminalTheme | None = None
        super().__init__()

    def compose(self) -> ComposeResult:
        yield containers.VerticalScroll(id="diff-container")
        yield widgets.Footer()

    @on(messages.TerminalThemeReport)
    def on_terminal_theme_report(self, event: messages.TerminalThemeReport) -> None:
        self.query_one(DiffView).terminal_theme = event.theme

    async def on_mount(self) -> None:
        try:
            diff_view = await DiffView.load(
                self.original,
                self.modified,
                split=self.split,
                annotations=self.annotations,
                wrap=self.wrap,
            )
        except LoadError as error:
            self.notify(str(error), title="Failed to load code", severity="error")
        else:
            diff_view.data_bind(DiffApp.split, DiffApp.annotations, DiffApp.wrap)
            await self.query_one("#diff-container").mount(diff_view)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print(
            "Usage python tdiff.py PATH1 PATH2\nTry: python tdiff.py example1.rs example2.rs"
        )
    else:
        app = DiffApp(sys.argv[1], sys.argv[2])
        app.run()
