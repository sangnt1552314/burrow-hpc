from typing import List, Optional

from textual.app import ComposeResult
from textual.widgets import Static

from hpit.core.models import Job
from hpit.tui.pages.base import Page
from hpit.tui.widgets.tables import JobTable


class LogsPage(Page):
    """Pick a job; Enter opens its stdout/stderr tail."""

    TITLE = "Logs"

    def __init__(self):
        super().__init__(id="logs")

    def compose(self) -> ComposeResult:
        yield Static("Choose a job to view its PBS output and error logs.", classes="message")
        yield JobTable(compact=True, id="logs-table")

    def show_jobs(self, jobs: List[Job], error: Optional[str]) -> None:
        message = self.query_one(".message", Static)
        if error:
            message.update(f"Unable to query PBS: {error}")
        elif not jobs:
            message.update("No active jobs. Press h on the Jobs page to include finished jobs.")
        else:
            message.update("Choose a job to view its PBS output and error logs.")
        self.main_widget().update_jobs(jobs if not error else [])

    def on_data_table_row_selected(self, event: JobTable.RowSelected) -> None:
        event.stop()
        self.app.open_job_logs(event.row_key.value)

    def main_widget(self) -> JobTable:
        return self.query_one("#logs-table", JobTable)
