from pathlib import Path
import sys

from textual.app import App, ComposeResult
from textual import widgets
from textual import containers

from textual_diff_view import DiffView

class DiffApp(App):
    BINDINGS = [
        ("space", "split", "Toggle split"),
        ("a", "toggle_annotations", "Toggle annotations"),
    ]

    def __init__(self, path1:Path, path2:Path) -> None:
        self.path1 = path1
        self.path2 = path2

        super(). __init__()
        

    def compose(self) -> ComposeResult:
        with containers.VerticalScroll(id="diff-container"):
            pass
        yield widgets.Footer()

    def on_mount(self) -> None:
        code1 = ""
        code2 = ""
        try:
            code1 = path1.read_text("utf-8")
        except OSError as error:
            self.notify(f"Unable to read {self.path1!r}\n\n{error}", title="Read Error", severity="error")
            
        try:
            code2 = path2.read_text("utf-8")
        except OSError as error:
            self.notify(f"Unable to read {self.path2!r}\n\n{error}", title="Read Error", severity="error")

        self.query_one("#diff-container").mount(DiffView(self.path1.name, self.path2.name, code1, code2))
        

    def action_split(self) -> None:
        self.query_one(DiffView).split = not self.query_one(DiffView).split

    def action_toggle_annotations(self) -> None:
        self.query_one(DiffView).annotations = not self.query_one(
            DiffView
        ).annotations

if __name__ == "__main__":
    from pathlib import Path

    if len(sys.argv) != 3:
        print("Usage python tdiff.py PATH1 PATH2\nTry: python tdiff.py")
    else:
        path1 = Path(sys.argv[1])
        path2 = Path(sys.argv[2])
        app = DiffApp(path1, path2)
        app.run()
