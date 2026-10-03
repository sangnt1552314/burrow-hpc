from typing import Optional

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Log, Static

from hpit.core import api, config
from hpit.core.models import JobDetails, LogTail
from hpit.tui.theme import MUTED
from hpit.tui.util import call_backend

FOLLOW_INTERVAL = 5


class LogScreen(Screen):
    """Tail of a job's stdout/stderr, using the paths PBS reports."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("o", "stream('stdout')", "stdout"),
        Binding("e", "stream('stderr')", "stderr"),
        Binding("f", "toggle_follow", "Follow"),
        Binding("r", "reload", "Refresh"),
    ]

    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id
        self.details: Optional[JobDetails] = None
        self.stream = "stdout"
        self.follow = False

    def compose(self) -> ComposeResult:
        with Vertical(id="log-panel", classes="panel"):
            yield Static("Loading…", id="log-info", classes="message")
            yield Log(id="log", highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        self._update_title()
        self.set_interval(FOLLOW_INTERVAL, self._follow_tick)
        self.query_one(Log).focus()
        self.action_reload()

    def _update_title(self) -> None:
        follow = " · following" if self.follow else ""
        self.query_one("#log-panel").border_title = (
            f"{self.stream} · job {self.job_id.split('.')[0]}{follow}"
        )

    def action_stream(self, stream: str) -> None:
        self.stream = stream
        self._update_title()
        self.action_reload()

    def action_toggle_follow(self) -> None:
        self.follow = not self.follow
        self._update_title()
        self.notify(f"Follow {'on' if self.follow else 'off'} (every {FOLLOW_INTERVAL}s)")

    def _follow_tick(self) -> None:
        if self.follow:
            self.action_reload()

    def action_reload(self) -> None:
        self.load_log(self.stream)

    @work(thread=True, exclusive=True)
    def load_log(self, stream: str) -> None:
        # Job details (and so the log paths) only need fetching once.
        if self.details is None:
            details, error = call_backend(api.get_job_details, self.job_id)
            if details is None:
                self.app.call_from_thread(self._show_result, stream, None, error)
                return
            self.details = details

        log, error = call_backend(api.tail_job_log, self.details, stream, config.LOG_LINES)
        self.app.call_from_thread(self._show_result, stream, log, error)

    def _show_result(self, stream: str, log: Optional[LogTail], error: Optional[str]) -> None:
        if stream != self.stream:
            return

        info = self.query_one("#log-info", Static)
        view = self.query_one(Log)
        at_bottom = view.is_vertical_scroll_end
        view.clear()

        if log is None:
            info.update(Text(error or "Could not read log.", style="#E06C75"))
            return

        text = Text(log.path, style=MUTED)
        text.append(f"   last {len(log.lines)} lines")
        if log.note:
            text.append(f"\n{log.note}", style="#E5C07B")
        info.update(text)

        if log.lines:
            view.write_lines(log.lines, scroll_end=at_bottom or not self.follow)
        else:
            view.write_line("(log is empty)")
