from typing import Optional

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from hpit.core import api
from hpit.core.models import JobDetails
from hpit.tui.util import call_backend, key_values, state_text


def _short_path(path: str, workdir: str) -> str:
    """Show log paths relative to the working directory when inside it."""
    if not path:
        return "--"
    if workdir and path.startswith(workdir.rstrip("/") + "/"):
        return "./" + path[len(workdir.rstrip("/")) + 1:]
    return path


class JobDetailsScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("l", "logs", "Logs"),
        Binding("k", "cancel_job", "Cancel job"),
        Binding("r", "reload", "Refresh"),
    ]

    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id
        self.details: Optional[JobDetails] = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="details", classes="panel") as panel:
            panel.border_title = f"Job {self.job_id.split('.')[0]}"
            yield Static("Loading job details…", id="details-title")
            with Horizontal(id="details-columns"):
                with Vertical(classes="box"):
                    yield Static("Job", classes="section-title")
                    yield Static("", id="details-job")
                with Vertical(classes="box"):
                    yield Static("Resources", classes="section-title")
                    yield Static("", id="details-resources")
            with Vertical(classes="box"):
                yield Static("Submission", classes="section-title")
                yield Static("", id="details-submission")
        yield Footer()

    def on_mount(self) -> None:
        self.action_reload()

    def action_reload(self) -> None:
        self.load_details()

    @work(thread=True, exclusive=True)
    def load_details(self) -> None:
        details, error = call_backend(api.get_job_details, self.job_id)
        self.app.call_from_thread(self._show_result, details, error)

    def _show_result(self, details: Optional[JobDetails], error: Optional[str]) -> None:
        title = self.query_one("#details-title", Static)
        if details is None:
            title.update(Text(error or "Could not load job.", style="#E06C75"))
            return

        self.details = details
        job = details.job
        title.update(Text(job.name, style="bold #E6EDF3"))

        self.query_one("#details-job", Static).update(key_values([
            ("Status", state_text(job)),
            ("Job ID", job.job_id),
            ("Queue", job.queue),
            ("Node", details.node),
            ("Exit status", details.exit_status),
            ("Comment", details.comment or "--"),
        ]))
        self.query_one("#details-resources", Static).update(key_values([
            ("GPU", str(job.gpus)),
            ("CPU", str(job.cpus)),
            ("Memory", f"{details.memory_used} used of {job.memory}"),
            ("Requested walltime", job.requested_walltime),
            ("Used walltime", job.runtime),
            ("CPU time", f"{details.cpu_time} ({details.cpu_percent})"),
        ]))
        stderr = _short_path(details.stderr_path, details.workdir)
        if details.stderr_joined:
            stderr = "merged into stdout (Join_Path=oe)"
        self.query_one("#details-submission", Static).update(key_values([
            ("Project", details.project),
            ("Script", details.script),
            ("Working directory", details.workdir),
            ("Submitted", details.submitted),
            ("Started", details.started),
            ("stdout", _short_path(details.stdout_path, details.workdir)),
            ("stderr", stderr),
        ]))

    def action_logs(self) -> None:
        self.app.open_job_logs(self.job_id)

    def action_cancel_job(self) -> None:
        if self.details:
            self.app.request_cancel(self.details.job)
