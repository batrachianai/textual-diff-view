from textual.app import App, ComposeResult
from textual import containers
from textual.reactive import var
from textual import widgets

from textual_diff_view import DiffView, LoadError


class DiffApp(App):
    """Simple app to display a diff between two files."""

    BINDINGS = [
        ("space", "toggle('split')", "Toggle split"),
        ("a", "toggle('annotations')", "Toggle annotations"),
        ("f", "toggle('fold')", "Toggle fold"),
    ]

    split = var(False)
    annotations = var(True)
    fold = var(True)

    def __init__(self, original: str, modified: str) -> None:
        self.original = original
        self.modified = modified
        super().__init__()

    def compose(self) -> ComposeResult:
        yield containers.VerticalScroll(id="diff-container")
        yield widgets.Footer()

    async def on_mount(self) -> None:
        try:
            diff_view = await DiffView.load(
                self.original,
                self.modified,
                split=self.split,
                annotations=self.annotations,
                fold=self.fold,
            )
        except LoadError as error:
            self.notify(str(error), title="Failed to load code", severity="error")
        else:
            diff_view.data_bind(DiffApp.split, DiffApp.annotations, DiffApp.fold)
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
