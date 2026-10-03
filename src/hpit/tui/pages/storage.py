import os
import time
from typing import List, Optional

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from hpit.core import api, config
from hpit.core.models import Quota, StorageScan
from hpit.core.units import human_bytes
from hpit.tui.pages.base import Page
from hpit.tui.theme import MUTED
from hpit.tui.util import call_backend, format_age, usage_bar
from hpit.tui.widgets.tables import NavTable

# Warn before du on locations this big; it can run for a very long time.
HUGE_FILE_COUNT = 1_000_000


class StoragePage(Page):
    """Storage locations with quotas, then per-folder sizes inside one.

    Locations (home, scratch, project folders) and their quotas come from
    site reports, so they are instant. Folder sizes need du, which only runs
    when asked: `s` on a location, or opening a sub-folder. Results are
    cached on disk so reopening HPIT shows the last scan.
    """

    TITLE = "Storage"

    BINDINGS = [
        Binding("s", "scan", "Scan sizes"),
        Binding("backspace", "up", "Back", show=False),
    ]

    def __init__(self):
        super().__init__(id="storage")
        self.quotas: List[Quota] = []
        # None while showing the location list.
        self.location: Optional[Quota] = None
        self.path = ""
        self.scanning: Optional[str] = None
        self.scan_started = 0.0

    def compose(self) -> ComposeResult:
        yield Static("Loading…", id="storage-path", classes="message")
        yield NavTable(id="storage-table")

    def on_mount(self) -> None:
        self.set_interval(1, self._tick)

    def load(self) -> None:
        self.load_quotas()

    # Locations

    @work(thread=True, exclusive=True, group="storage-quotas")
    def load_quotas(self) -> None:
        quotas, error = call_backend(api.get_quotas)
        quotas = quotas or []
        # Without a scratch report (e.g. another cluster), fall back to df.
        if not any(q.name == "Scratch" for q in quotas):
            usage, df_error = call_backend(api.get_disk_usage, config.SCRATCH)
            if usage:
                quotas.append(Quota("Scratch", usage.path, usage.used_bytes, usage.total_bytes))
            error = error or df_error
        self.app.call_from_thread(self._quotas_loaded, quotas, error)

    def _quotas_loaded(self, quotas: List[Quota], error: Optional[str]) -> None:
        self.quotas = quotas
        if not quotas:
            self._set_status(Text(error or "No storage locations found.", style="#E06C75"))
            return
        if self.location is None:
            self._show_locations()
        else:
            # Refresh the current location's quota line.
            self.location = next((q for q in quotas if q.path == self.location.path), self.location)
            self._show_path(self.path, scan_if_missing=False)

    def _show_locations(self, select: Optional[str] = None) -> None:
        self.location = None
        self.path = ""
        self.refresh_bindings()

        table = self.query_one("#storage-table", NavTable)
        table.clear(columns=True)
        table.add_columns("Location", "Path", "Quota", "", "Used", "Files")
        for q in self.quotas:
            color = _quota_color(q)
            table.add_row(
                Text(q.name, style="bold"),
                Text(q.path, style="#61AFEF"),
                usage_bar(q.percent / 100, 20, color) if q.known else Text("quota unknown", style=MUTED),
                Text(f"{q.percent:.0f}%" if q.known else "", style=color, justify="right"),
                Text(f"{human_bytes(q.used_bytes)} / {human_bytes(q.limit_bytes)}" if q.known else "",
                     justify="right"),
                Text(f"{q.files:,}" if q.files is not None else "", justify="right", style=MUTED),
                key=q.path,
            )
        if select and select in table.rows:
            table.move_cursor(row=table.get_row_index(select))

        ages = [q.reported_at for q in self.quotas if q.reported_at]
        age = f" · quota reports from {format_age(min(ages))}" if ages else ""
        self._set_status(Text(f"Choose a location (→ or Enter to open){age}", style=MUTED))

    # Folders

    def _show_path(self, path: str, scan_if_missing: bool) -> None:
        self.path = path
        self.refresh_bindings()
        cached = api.load_cached_scan(path)
        if cached:
            self._render_scan(cached)
            return

        table = self.query_one("#storage-table", NavTable)
        table.clear(columns=True)
        table.add_columns("Name", "Size", "Share", "")
        if scan_if_missing:
            self.action_scan()
        else:
            self._set_status(self._header(
                Text("Not scanned yet. Press s to measure folder sizes (du can take several minutes).", style=MUTED)
            ))

    def _header(self, detail: Text) -> Text:
        """Location quota line + current path + a detail line."""
        text = Text()
        q = self.location
        if q is not None:
            text.append(f"{q.name}  ", style="bold")
            if q.known:
                color = _quota_color(q)
                text.append_text(usage_bar(q.percent / 100, 24, color))
                text.append(f" {q.percent:.0f}%", style=color)
                text.append(f"  {human_bytes(q.used_bytes)} of {human_bytes(q.limit_bytes)}", style=MUTED)
                if q.files is not None:
                    text.append(f" · {q.files:,} files", style=MUTED)
            text.append("\n")
        text.append(self.path, style="#61AFEF")
        text.append("\n")
        text.append_text(detail)
        return text

    def action_scan(self) -> None:
        if not self.path:
            return
        if self.scanning:
            self.notify(f"Already scanning {self.scanning}")
            return
        q = self.location
        if q and self.path == q.path and q.files and q.files > HUGE_FILE_COUNT:
            self.notify(
                f"{q.name} holds {q.files:,} files; du may take a very long time "
                "(it stops after 15 min). Opening a sub-folder is faster.",
                severity="warning", timeout=10,
            )
        self.scanning = self.path
        self.scan_started = time.time()
        self._tick()
        self.run_scan(self.path)

    @work(thread=True, group="storage-du")
    def run_scan(self, path: str) -> None:
        scan, error = call_backend(api.scan_directory, path)
        self.app.call_from_thread(self._scan_finished, path, scan, error)

    def _scan_finished(self, path: str, scan: Optional[StorageScan], error: Optional[str]) -> None:
        self.scanning = None
        if path != self.path:
            if scan:
                self.notify(f"Finished scanning {path}")
            return
        if scan:
            self._render_scan(scan)
        else:
            self._set_status(self._header(Text(error or "Scan failed.", style="#E06C75")))

    def _tick(self) -> None:
        if self.scanning and self.scanning == self.path:
            elapsed = int(time.time() - self.scan_started)
            self._set_status(self._header(
                Text(f"Scanning with du… {elapsed}s (large folders can take minutes)", style="#E5C07B")
            ))

    def _render_scan(self, scan: StorageScan) -> None:
        table = self.query_one("#storage-table", NavTable)
        table.clear(columns=True)
        table.add_columns("Name", "Size", "Share", "")
        biggest = max((e.size_bytes for e in scan.entries), default=0) or 1
        for entry in scan.entries:
            name = Text(entry.name + ("/" if entry.is_dir else ""), style="#61AFEF" if entry.is_dir else "")
            share = entry.size_bytes / scan.total_bytes if scan.total_bytes else 0
            table.add_row(
                name,
                Text(human_bytes(entry.size_bytes), justify="right"),
                usage_bar(entry.size_bytes / biggest, 24),
                Text(f"{share:.0%}", style=MUTED, justify="right"),
                key=entry.path if entry.is_dir else None,
            )
        note = " · some folders were unreadable" if scan.incomplete else ""
        self._set_status(self._header(Text(
            f"{human_bytes(scan.total_bytes)} in this folder · scanned {format_age(scan.scanned_at)}{note}",
            style=MUTED,
        )))

    def _set_status(self, text) -> None:
        self.query_one("#storage-path", Static).update(text)

    # Navigation: → / Enter opens, ← / Backspace goes back up.

    def on_data_table_row_selected(self, event: NavTable.RowSelected) -> None:
        event.stop()
        key = event.row_key.value
        if self.location is None:
            self.location = next((q for q in self.quotas if q.path == key), None)
            if self.location:
                self._show_path(self.location.path, scan_if_missing=False)
        # Only folder rows have a key (the "(files)" row has none).
        elif key and key != self.path:
            self._show_path(key, scan_if_missing=True)

    def check_action(self, action: str, parameters) -> Optional[bool]:
        if action == "scan":
            return bool(self.path)
        return True

    def action_up(self) -> None:
        if self.location is None:
            return
        if self.path == self.location.path:
            self._show_locations(select=self.location.path)
        else:
            child = self.path
            self._show_path(os.path.dirname(self.path), scan_if_missing=False)
            table = self.query_one("#storage-table", NavTable)
            # Keep the cursor on the folder we came from (if the parent is scanned).
            if child in table.rows:
                table.move_cursor(row=table.get_row_index(child))

    def main_widget(self) -> NavTable:
        return self.query_one("#storage-table", NavTable)


def _quota_color(q: Quota) -> str:
    return "#E06C75" if q.percent >= 90 else "#E5C07B" if q.percent >= 75 else "#61AFEF"
