from typing import List, Optional

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from hpit.core import api, config
from hpit.core.models import DiskUsage, Job
from hpit.core.units import human_bytes
from hpit.tui.pages.base import Page
from hpit.tui.util import call_backend, key_values, usage_bar
from hpit.tui.widgets.tables import JobTable


class OverviewPage(Page):
    TITLE = "Overview"

    def __init__(self):
        super().__init__(id="overview")
        # Either summary rows, or a message (loading / PBS error).
        self.job_rows: list = []
        self.jobs_message: Optional[Text] = Text("Loading jobs...")
        self.scratch_summary = Text("--")

    def compose(self) -> ComposeResult:
        with Vertical(id="system-box", classes="box"):
            yield Static("System", classes="section-title")
            yield Static("Loading...", id="system-summary")
        with Vertical(id="recent-box", classes="box"):
            yield Static("Active jobs", classes="section-title")
            yield Static("", id="recent-message", classes="message")
            yield JobTable(compact=True, id="recent-jobs")

    def load(self) -> None:
        self.load_disk_usage()

    @work(thread=True, exclusive=True, group="overview-disk")
    def load_disk_usage(self) -> None:
        usage, error = call_backend(api.get_disk_usage, config.SCRATCH)
        self.app.call_from_thread(self._show_disk_usage, usage, error)

    def _show_disk_usage(self, usage: Optional[DiskUsage], error: Optional[str]) -> None:
        if usage is None:
            self.scratch_summary = Text(error or "--", style="#E06C75")
        else:
            self.scratch_summary = usage_bar(usage.percent / 100, 20)
            self.scratch_summary.append(
                f"  {usage.percent:.0f}%  "
                f"{human_bytes(usage.used_bytes)} / {human_bytes(usage.total_bytes)}"
            )
        self._render_summary()

    def show_jobs(self, jobs: List[Job], error: Optional[str]) -> None:
        message = self.query_one("#recent-message", Static)
        table = self.query_one("#recent-jobs", JobTable)

        if error:
            self.jobs_message = Text.assemble(("Unable to query PBS: ", "#E06C75"), error)
            message.update("--")
            message.display = True
            table.update_jobs([])
        else:
            active = [job for job in jobs if job.state != "F"]
            running = [job for job in active if job.state == "R"]
            self.jobs_message = None
            self.job_rows = [
                ("Running jobs", Text(str(len(running)), style="bold #98C379")),
                ("Queued jobs", Text(str(sum(j.state == "Q" for j in active)), style="bold #E5C07B")),
                ("Held jobs", Text(str(sum(j.state == "H" for j in active)), style="bold")),
                ("GPUs in use", Text(str(sum(j.gpus for j in running)), style="bold")),
            ]
            message.update("" if active else "No active jobs.")
            message.display = not active
            table.update_jobs(active)

        self._render_summary()

    def _render_summary(self) -> None:
        scratch = ("Scratch usage", self.scratch_summary)
        if self.jobs_message is None:
            text = key_values(self.job_rows + [scratch])
        else:
            text = self.jobs_message.copy()
            text.append("\n\n")
            text.append_text(key_values([scratch]))
        self.query_one("#system-summary", Static).update(text)

    def main_widget(self):
        return self.query_one("#recent-jobs", JobTable)

    def on_data_table_row_selected(self, event: JobTable.RowSelected) -> None:
        event.stop()
        self.app.open_job_details(event.row_key.value)
