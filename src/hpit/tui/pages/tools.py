from typing import List, Optional, Tuple

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.widgets import DataTable, Static

from hpit.core import api
from hpit.tui.pages.base import Page
from hpit.tui.theme import MUTED
from hpit.tui.util import call_backend


class ToolsPage(Page):
    """Doctor: quick local diagnostics (same data as `hpit doctor`)."""

    TITLE = "Tools · Doctor"

    def __init__(self):
        super().__init__(id="tools")

    def compose(self) -> ComposeResult:
        yield Static("Checking…", classes="message")
        yield DataTable(id="doctor-table", show_cursor=False)

    def on_mount(self) -> None:
        self.query_one("#doctor-table", DataTable).add_columns("Check", "Value")

    def load(self) -> None:
        self.run_doctor()

    @work(thread=True, exclusive=True, group="doctor")
    def run_doctor(self) -> None:
        rows, error = call_backend(api.get_doctor)
        self.app.call_from_thread(self._show_result, rows, error)

    def _show_result(self, rows: Optional[List[Tuple[str, str]]], error: Optional[str]) -> None:
        message = self.query_one(".message", Static)
        table = self.query_one("#doctor-table", DataTable)
        table.clear()
        if rows is None:
            message.update(Text(error or "Doctor failed.", style="#E06C75"))
            return
        message.update("Environment and configuration. Set HPIT_* variables to override defaults.")
        for name, value in rows:
            style = "#E06C75" if "not found" in value or "unavailable" in value else ""
            table.add_row(Text(name, style=MUTED), Text(value, style=style))

    def main_widget(self) -> DataTable:
        return self.query_one("#doctor-table", DataTable)
