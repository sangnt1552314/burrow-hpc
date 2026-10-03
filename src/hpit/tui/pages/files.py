import os
from typing import List, Optional

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from hpit.core import api, config
from hpit.core.models import FileEntry
from hpit.core.units import human_bytes
from hpit.tui.pages.base import Page
from hpit.tui.theme import MUTED
from hpit.tui.util import call_backend, format_time
from hpit.tui.widgets.tables import Table


LARGE_FILE_MB = 1024


class FilesPage(Page):
    """Read-only browser for common HPC locations. No delete on purpose."""

    TITLE = "Files"

    BINDINGS = [
        Binding("backspace", "up", "Up"),
        Binding("s", "go('scratch')", "Scratch"),
        Binding("tilde", "go('home')", "Home", key_display="~"),
        Binding("b", "large_files", "Big files"),
    ]

    def __init__(self):
        super().__init__(id="files")
        self.path = os.path.normpath(config.SCRATCH)
        # "browse" a directory, or show "large" files found under it.
        self.mode = "browse"
        self.dirs = set()

    def compose(self) -> ComposeResult:
        yield Static("", id="files-path", classes="message")
        yield Table(id="files-table")

    def on_mount(self) -> None:
        self.query_one("#files-table", Table).add_columns("Name", "Size", "Modified")

    def load(self) -> None:
        self.open_path(self.path)

    def open_path(self, path: str) -> None:
        self.path = os.path.normpath(path)
        self.mode = "browse"
        self._set_status(f"{self.path}\nLoading…")
        self.refresh_bindings()
        self.list_files(self.path)

    @work(thread=True, exclusive=True, group="files")
    def list_files(self, path: str) -> None:
        entries, error = call_backend(api.list_directory, path)
        self.app.call_from_thread(self._show_result, path, entries, error, "browse")

    def action_large_files(self) -> None:
        self.mode = "large"
        self._set_status(f"{self.path}\nSearching for files over {LARGE_FILE_MB // 1024} GB… (find can take a while)")
        self.query_one("#files-table", Table).clear()
        self.refresh_bindings()
        self.search_large(self.path)

    @work(thread=True, exclusive=True, group="files")
    def search_large(self, path: str) -> None:
        entries, error = call_backend(api.find_large_files, path, LARGE_FILE_MB)
        self.app.call_from_thread(self._show_result, path, entries, error, "large")

    def _show_result(self, path: str, entries: Optional[List[FileEntry]], error: Optional[str], mode: str) -> None:
        if path != self.path or mode != self.mode:
            return  # The user moved on while this was loading.

        table = self.query_one("#files-table", Table)
        table.clear()
        self.dirs = {e.path for e in entries or [] if e.is_dir}
        if entries is None:
            self._set_status(Text(f"{path}\n{error}", style="#E06C75"))
            return

        for entry in entries:
            if entry.is_dir:
                name = Text(entry.name + "/", style="#61AFEF")
                size = Text("", justify="right")
            else:
                name = Text(entry.name, style="#56B6C2" if entry.kind == "l" else "")
                size = Text(human_bytes(entry.size_bytes), justify="right")
            table.add_row(name, size, Text(format_time(entry.modified), style=MUTED), key=entry.path)

        if mode == "large":
            total = sum(e.size_bytes for e in entries)
            self._set_status(
                f"{path}\n{len(entries)} files over {LARGE_FILE_MB // 1024} GB "
                f"({human_bytes(total)}) · Backspace to go back"
            )
        else:
            self._set_status(f"{path}\n{len(entries)} items")

    def _set_status(self, text) -> None:
        self.query_one("#files-path", Static).update(text)

    def on_data_table_row_selected(self, event: Table.RowSelected) -> None:
        event.stop()
        path = event.row_key.value
        if path in self.dirs:
            self.open_path(path)

    def check_action(self, action: str, parameters) -> Optional[bool]:
        if action == "up":
            return self.mode == "large" or self.path != "/"
        return True

    def action_up(self) -> None:
        if self.mode == "large":
            self.open_path(self.path)
        else:
            self.open_path(os.path.dirname(self.path))

    def action_go(self, place: str) -> None:
        self.open_path(config.SCRATCH if place == "scratch" else os.path.expanduser("~"))

    def main_widget(self) -> Table:
        return self.query_one("#files-table", Table)
