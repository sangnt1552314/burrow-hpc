from typing import List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Input, Static

from hpit.core.models import Job
from hpit.tui.pages.base import Page
from hpit.tui.widgets.tables import JobTable


class JobsPage(Page):
    TITLE = "Jobs"

    BINDINGS = [
        Binding("l", "logs", "Logs"),
        Binding("k", "cancel_job", "Cancel job"),
        Binding("slash", "search", "Search", key_display="/"),
        Binding("h", "toggle_history", "History"),
        Binding("escape", "close_search", "Clear search"),
    ]

    def __init__(self):
        super().__init__(id="jobs")
        self.jobs: List[Job] = []
        self.query_text = ""

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Filter by name, ID, state or queue…", id="job-search")
        yield Static("Loading jobs...", id="jobs-message", classes="message")
        yield JobTable(id="jobs-table")

    def on_mount(self) -> None:
        self.query_one("#job-search", Input).display = False

    def show_jobs(self, jobs: List[Job], error: Optional[str]) -> None:
        message = self.query_one("#jobs-message", Static)
        if error:
            message.update(f"Unable to query PBS: {error}")
            message.display = True
            return

        # Active jobs first, newest history last.
        self.jobs = sorted(jobs, key=lambda job: job.state == "F")
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = self.query_text.lower()
        shown = [
            job for job in self.jobs
            if not needle or any(
                needle in field.lower()
                for field in (job.job_id, job.name, job.state_name, job.queue)
            )
        ]
        self.query_one("#jobs-table", JobTable).update_jobs(shown)

        message = self.query_one("#jobs-message", Static)
        history = " (including finished)" if self.app.include_finished else ""
        if not self.jobs:
            message.update(f"No active jobs{history}.")
        elif not shown:
            message.update(f"No jobs match '{self.query_text}'.")
        else:
            message.update(f"{len(shown)} jobs{history}" + (f" matching '{self.query_text}'" if needle else ""))
        message.display = True

    def check_action(self, action: str, parameters) -> Optional[bool]:
        search = self.query_one("#job-search", Input)
        if action == "close_search":
            # Only claim Escape while searching; otherwise it means "back".
            return search.display or bool(self.query_text)
        if search.has_focus and action in ("logs", "cancel_job", "toggle_history", "search"):
            return False  # Let those keys type into the search box.
        return True

    def action_search(self) -> None:
        search = self.query_one("#job-search", Input)
        search.display = True
        search.focus()
        self.refresh_bindings()

    def action_close_search(self) -> None:
        search = self.query_one("#job-search", Input)
        search.value = ""
        search.display = False
        self.query_text = ""
        self._apply_filter()
        self.main_widget().focus()
        self.refresh_bindings()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.query_text = event.value.strip()
        self._apply_filter()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.main_widget().focus()

    def action_toggle_history(self) -> None:
        self.app.set_include_finished(not self.app.include_finished)

    def on_data_table_row_selected(self, event: JobTable.RowSelected) -> None:
        event.stop()
        self.app.open_job_details(event.row_key.value)

    def action_logs(self) -> None:
        job = self.main_widget().selected_job()
        if job:
            self.app.open_job_logs(job.job_id)

    def action_cancel_job(self) -> None:
        job = self.main_widget().selected_job()
        if job:
            self.app.request_cancel(job)

    def main_widget(self) -> JobTable:
        return self.query_one("#jobs-table", JobTable)
