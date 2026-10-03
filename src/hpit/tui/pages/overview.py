from typing import List, Optional, Tuple

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from hpit.core import api, config
from hpit.core.models import Job, Quota
from hpit.core.units import human_bytes
from hpit.tui.pages.base import Page
from hpit.tui.theme import MUTED
from hpit.tui.util import call_backend, key_values, usage_bar
from hpit.tui.widgets.tables import JobTable

Row = Tuple[str, Text]


class OverviewPage(Page):
    TITLE = "Overview"

    def __init__(self):
        super().__init__(id="overview")
        # Either job summary rows, or a message (loading / PBS error).
        self.job_rows: List[Row] = []
        self.jobs_message: Optional[Text] = Text("Loading jobs...")
        self.cluster_rows: List[Row] = [("Free GPUs", Text("…", style=MUTED))]
        self.storage_rows: List[Row] = [("Scratch", Text("…", style=MUTED))]
        self.project_rows: List[Row] = [("Projects", Text("…", style=MUTED))]

    def compose(self) -> ComposeResult:
        with Vertical(id="system-box", classes="box"):
            yield Static("System", classes="section-title")
            yield Static("Loading...", id="system-summary")
        with Vertical(id="recent-box", classes="box"):
            yield Static("Active jobs", classes="section-title")
            yield Static("", id="recent-message", classes="message")
            yield JobTable(compact=True, id="recent-jobs")

    def load(self) -> None:
        self.load_storage()
        self.load_cluster()
        self.load_projects()

    @work(thread=True, exclusive=True, group="overview-storage")
    def load_storage(self) -> None:
        quotas, error = call_backend(api.get_quotas)
        if not quotas:
            usage, error = call_backend(api.get_disk_usage, config.SCRATCH)
            quotas = [Quota("Scratch", usage.path, usage.used_bytes, usage.total_bytes)] if usage else []
        rows = [(q.name, self._quota_text(q)) for q in quotas] or [
            ("Scratch", Text(error or "--", style="#E06C75"))
        ]
        self.app.call_from_thread(self._set_rows, "storage_rows", rows)

    @work(thread=True, exclusive=True, group="overview-cluster")
    def load_cluster(self) -> None:
        status, error = call_backend(api.get_cluster_status)
        if status is None:
            value = Text(error or "--", style="#E06C75")
        else:
            value = Text(str(status.gpus_free), style="bold #98C379" if status.gpus_free else "bold #E06C75")
            value.append(f" of {status.gpus_total} on the cluster", style=MUTED)
        self.app.call_from_thread(self._set_rows, "cluster_rows", [("Free GPUs", value)])

    @work(thread=True, exclusive=True, group="overview-projects")
    def load_projects(self) -> None:
        projects, error = call_backend(api.get_projects)
        if projects is None:
            rows = [("Projects", Text("not logged in to amgr · see Projects page", style=MUTED))]
        else:
            current = [p for p in projects if p.active and not p.ended]
            rows = [
                (p.name, Text(f"{p.gpu_hours_left:,.0f}", style="bold").append(
                    f" GPU-h left of {p.gpu_hours_total:,.0f}", style=MUTED))
                for p in current
            ] or [("Projects", Text("no active projects", style=MUTED))]
        self.app.call_from_thread(self._set_rows, "project_rows", rows)

    @staticmethod
    def _quota_text(q: Quota) -> Text:
        text = usage_bar(q.percent / 100, 20)
        text.append(f"  {q.percent:.0f}%  {human_bytes(q.used_bytes)} / {human_bytes(q.limit_bytes)}")
        return text

    def _set_rows(self, name: str, rows: List[Row]) -> None:
        setattr(self, name, rows)
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
        other = self.cluster_rows + self.storage_rows + self.project_rows
        if self.jobs_message is None:
            text = key_values(self.job_rows + other)
        else:
            text = self.jobs_message.copy()
            text.append("\n\n")
            text.append_text(key_values(other))
        self.query_one("#system-summary", Static).update(text)

    def main_widget(self):
        return self.query_one("#recent-jobs", JobTable)

    def on_data_table_row_selected(self, event: JobTable.RowSelected) -> None:
        event.stop()
        self.app.open_job_details(event.row_key.value)
