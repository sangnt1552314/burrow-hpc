from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from hpit.core.models import Job
from hpit.tui.theme import MUTED
from hpit.tui.util import key_values


class ConfirmCancelScreen(ModalScreen):
    """Ask before `qdel`. Returns True only if "Cancel job" is pressed."""

    BINDINGS = [Binding("escape", "dismiss(False)", "Keep job")]

    def __init__(self, job: Job):
        super().__init__()
        self.job = job

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog", classes="panel danger") as dialog:
            dialog.border_title = "Cancel job?"
            yield Static(key_values([
                ("Job ID", Text(self.job.job_id, style="bold")),
                ("Name", Text(self.job.name, style="bold")),
                ("Status", self.job.state_name),
            ]))
            yield Static(
                Text("This runs qdel and cannot be undone.", style=MUTED),
                classes="message",
            )
            with Horizontal(id="dialog-buttons"):
                yield Button("Keep job", id="keep", variant="default")
                yield Button("Cancel job", id="confirm", variant="error")

    def on_mount(self) -> None:
        # Safe default: Enter right away keeps the job.
        self.query_one("#keep", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


HELP_TEXT = [
    ("Anywhere", [
        ("↑ ↓", "Move"),
        ("Enter", "Open"),
        ("Esc", "Back"),
        ("1 – 6", "Jump to a page"),
        ("r", "Refresh"),
        ("?", "This help"),
        ("q", "Quit"),
    ]),
    ("Jobs", [
        ("/", "Filter jobs"),
        ("h", "Show / hide finished jobs"),
        ("l", "Logs of selected job"),
        ("k", "Cancel selected job (asks first)"),
    ]),
    ("Logs", [("o / e", "stdout / stderr"), ("f", "Follow (auto refresh)")]),
    ("Storage", [("s", "Scan folder sizes (du)"), ("Backspace", "Up a folder")]),
    ("Files", [("b", "Find files over 1 GB"), ("s / ~", "Scratch / home"), ("Backspace", "Up")]),
]


class HelpScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close", show=False),
        Binding("q", "dismiss", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        text = Text()
        for i, (section, keys) in enumerate(HELP_TEXT):
            if i:
                text.append("\n\n")
            text.append(section, style="bold #61AFEF")
            for key, action in keys:
                text.append(f"\n  {key:<11}", style="#E5C07B")
                text.append(action)
        with Vertical(id="help", classes="panel") as panel:
            panel.border_title = "Help"
            yield Static(text)
