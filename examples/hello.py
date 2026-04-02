from textual.app import App, ComposeResult
from textual import containers

from textual_diff_view import DiffView

HELLO1 = """
def greet():
    print "Hello!"

greet()
"""

HELLO2 = """
def greet(name:str):
    print(f"Hello, {name}!")

greet('Will')
"""


class Hello(App):
    def compose(self) -> ComposeResult:
        with containers.VerticalScroll():
            yield DiffView("hello1.py", "hello2.py", HELLO1, HELLO2)


Hello().run()
