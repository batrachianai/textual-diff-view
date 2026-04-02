# Textual Diff View

Currently a WIP. 

Textual Diff View is a [Textual](https://github.com/textualize/textual) widget to display beautiful diffs in your terminal application.
Originally built for [Toad](https://github.com/batrachianai/toad), Textual Diff View may be used standalone.

![Diff Banner](images/diffbanner.png)

## Screenshots

<table>
<tr>  
<td>
  
![Split dark](images/split_dark.png)

</td>
<td>
  
![Unified dark](images/unified_dark.png)

</td>
</tr>

<tr>
<td>
  
![spliut light](images/split_light.png)

</td>

<td>
  
![Unified light](images/unified_light.png)

</td>

</tr>
</table>

## Features

The `DiffView` widget displays two version of a file with syntax and changes clearly highlighted.
Deleted lines / characters are shown with a red highlight.
Added lines / characters are shown with a green highlight.

There are two layout options; a *unified* view which shows the two files top-to-bottom with highlights, and a *split* view which shoiws the two files next to each other.

`DiffView` can also display annotations ("+" and "-" for added and deleted), to improve readability for color blind users.

Textual's theming system provides a variety of themes for the diff view, both light and dark.

## Examples

The following is a simple app to display a diff between two files from the command line.

```python
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
    ]

    split = var(True)
    annotations = var(True)

    def __init__(self, original: str, modified: str) -> None:
        self.original = original
        self.modified = modified
        super().__init__()

    def compose(self) -> ComposeResult:
        yield containers.VerticalScroll(id="diff-container")
        yield widgets.Footer()

    async def on_mount(self) -> None:
        try:
            diff_view = await DiffView.load(self.original, self.modified)
        except LoadError as error:
            self.notify(str(error), title="Failed to load code", severity="error")
        else:
            diff_view.data_bind(DiffApp.split, DiffApp.annotations)
            await self.query_one("#diff-container").mount(diff_view)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage python tdiff.py PATH1 PATH2\nTry: python tdiff.py")
    else:
        app = DiffApp(sys.argv[1], sys.argv[2])
        app.run()
```

You can find this file in the `examples/` directory.
Run it with the following:

```
uv run python tdiff.py example1.rs example2.rs
```

Use <kbd>space</kbd> to toggle unified / split, and <kbd>a</kbd> to toggle annotations.
