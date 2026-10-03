from typing import List

from rich.text import Text
from textual.binding import Binding
from textual.widgets import DataTable

from hpit.core.models import Job
from hpit.tui.util import state_text, truncate


class Table(DataTable):
    """A row-cursor DataTable whose footer shows Enter."""

    BINDINGS = [Binding("enter", "select_cursor", "Open")]

    def __init__(self, **kwargs):
        super().__init__(cursor_type="row", **kwargs)

    def selected_key(self):
        if self.row_count == 0:
            return None
        row_key, _ = self.coordinate_to_cell_key(self.cursor_coordinate)
        return row_key.value


class JobTable(Table):
    """Jobs keyed by full job ID; keeps the cursor on the same job across refreshes."""

    FULL = ("ID", "Name", "Status", "Queue", "GPU", "CPU", "Memory", "Runtime", "Walltime")
    COMPACT = ("ID", "Name", "Status", "Runtime")

    def __init__(self, compact: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.compact = compact
        self.jobs = {}

    def on_mount(self) -> None:
        self.add_columns(*(self.COMPACT if self.compact else self.FULL))

    def update_jobs(self, jobs: List[Job]) -> None:
        selected = self.selected_key()
        self.jobs = {job.job_id: job for job in jobs}
        self.clear()

        name_width = 52 if self.compact else 48
        for job in jobs:
            name = Text(truncate(job.name, name_width))
            if self.compact:
                row = (job.short_id, name, state_text(job), job.runtime)
            else:
                row = (
                    job.short_id, name, state_text(job), job.queue,
                    str(job.gpus), str(job.cpus), job.memory,
                    job.runtime, job.requested_walltime,
                )
            self.add_row(*row, key=job.job_id)

        if selected in self.jobs:
            self.move_cursor(row=self.get_row_index(selected))

    def selected_job(self):
        return self.jobs.get(self.selected_key())
