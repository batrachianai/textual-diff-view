from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual_diff_view import DiffView

HELLO1 = """
def greet():
    print "Hello!"

greet()

# Heard joke once: Man goes to doctor.
# Says he's depressed.
# Says life seems harsh and cruel.
# Says he feels all alone in a threatening world where what lies ahead is vague and uncertain.
# Doctor says: 'Treatment is simple. Great clown Pagliacci is in town. Go and see him. That should pick you up.'
# Man bursts into tears. Says: 'But doctor... I am Pagliacci.

for n in range(10):
    print("Foo")
"""

HELLO2 = '''
def greet(name:str):
    """Greet anyone""" 
    print(f"Hello, {name}!")

greet('Will')

# Heard joke once: Man goes to doctor.
# Says he's depressed.
# Says life seems harsh and cruel.
# Says he feels all alone in a threatening world where what lies ahead is vague and uncertain.
# Doctor says: 'Treatment is simple. Great clown Pagliacci is in town. Go and see him. That should pick you up.'
# Man bursts into tears. Says: 'But doctor... I am Pagliacci.

for n in range(10):
    print("Bar")
'''


class DiffApp(App):

    def on_load(self):
        self.theme = "dracula"

    def compose(self) -> ComposeResult:
        yield DiffView("hello1.py", "hello2.py", HELLO1, HELLO2)


def test_diff_view_defaults(snap_compare):
    assert snap_compare(DiffApp())


def test_diff_view_unified(snap_compare):
    def run_before(pilot: Pilot):
        pilot.app.query_one(DiffView).split = False

    assert snap_compare(DiffApp(), run_before=run_before)


def test_diff_view_annotations(snap_compare):
    def run_before(pilot: Pilot):
        pilot.app.query_one(DiffView).annotations = True

    assert snap_compare(DiffApp(), run_before=run_before)


def test_diff_view_unified_annotations(snap_compare):
    def run_before(pilot: Pilot):
        pilot.app.query_one(DiffView).split = False
        pilot.app.query_one(DiffView).annotations = True

    assert snap_compare(DiffApp(), run_before=run_before)


def test_diff_view_wrap_split(snap_compare):
    def run_before(pilot: Pilot):
        pilot.app.query_one(DiffView).wrap = True

    assert snap_compare(DiffApp(), run_before=run_before)


def test_diff_view_wrap_split_annotations(snap_compare):
    def run_before(pilot: Pilot):
        pilot.app.query_one(DiffView).wrap = True
        pilot.app.query_one(DiffView).annotations = True

    assert snap_compare(DiffApp(), run_before=run_before)


def test_diff_view_wrap_unified(snap_compare):
    def run_before(pilot: Pilot):
        pilot.app.query_one(DiffView).wrap = True
        pilot.app.query_one(DiffView).split = False

    assert snap_compare(DiffApp(), run_before=run_before)


def test_diff_view_wrap_unified_annotations(snap_compare):
    def run_before(pilot: Pilot):
        pilot.app.query_one(DiffView).wrap = True
        pilot.app.query_one(DiffView).split = False
        pilot.app.query_one(DiffView).annotations = True

    assert snap_compare(DiffApp(), run_before=run_before)
