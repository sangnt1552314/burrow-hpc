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
from hpit.tui.widgets.tables import Table


class StoragePage(Page):
    """Scratch quota (instant, via df) plus per-folder sizes (slow, via du).

    du only runs when asked: `s` on the scratch root, or Enter on a folder.
    Results are cached on disk so reopening HPIT shows the last scan.
    """

    TITLE = "Storage"

    BINDINGS = [
        Binding("s", "scan", "Scan"),
        Binding("backspace", "up", "Up"),
    ]

    def __init__(self):
        super().__init__(id="storage")
        self.root = os.path.normpath(config.SCRATCH)
        self.path = self.root
        self.scanning: Optional[str] = None
        self.scan_started = 0.0

    def compose(self) -> ComposeResult:
        yield Static("Loading...", id="storage-usage", classes="box")
        yield Static("", id="storage-path", classes="message")
        yield Table(id="storage-table")

    def on_mount(self) -> None:
        self.query_one("#storage-table", Table).add_columns("Name", "Size", "Share", "")
        self.set_interval(1, self._tick)

    def load(self) -> None:
        self.load_usage()
        self._show_path(self.path, scan_if_missing=False)

    @work(thread=True, exclusive=True, group="storage-df")
    def load_usage(self) -> None:
        # Site quota reports (home + scratch); fall back to df for scratch.
        quotas, _ = call_backend(api.get_quotas)
        quotas = quotas or []
        if not any(q.name == "Scratch" for q in quotas):
            usage, error = call_backend(api.get_disk_usage, self.root)
            if usage:
                quotas.append(Quota("Scratch", usage.path, usage.used_bytes, usage.total_bytes))
            elif not quotas:
                self.app.call_from_thread(self._render_usage, [], error)
                return
        self.app.call_from_thread(self._render_usage, quotas, None)

    def _render_usage(self, quotas: List[Quota], error: Optional[str]) -> None:
        box = self.query_one("#storage-usage", Static)
        if not quotas:
            box.update(Text(error or "--", style="#E06C75"))
            return

        text = Text()
        for i, q in enumerate(quotas):
            color = "#E06C75" if q.percent >= 90 else "#E5C07B" if q.percent >= 75 else "#61AFEF"
            if i:
                text.append("\n\n")
            text.append(f"{q.name:<9}", style="bold")
            text.append_text(usage_bar(q.percent / 100, 36, color))
            text.append(f"  {q.percent:.0f}%", style=color)
            details = f"   {human_bytes(q.used_bytes)} of {human_bytes(q.limit_bytes)}"
            if q.files is not None:
                details += f" · {q.files:,} files"
            if q.reported_at:
                details += f" · report {format_age(q.reported_at)}"
            text.append(details, style=MUTED)
        box.update(text)

    def _show_path(self, path: str, scan_if_missing: bool) -> None:
        self.path = path
        cached = api.load_cached_scan(path)
        if cached:
            self._render_scan(cached)
        else:
            self.query_one("#storage-table", Table).clear()
            if scan_if_missing:
                self.action_scan()
            else:
                self._set_status(f"{path}\nNot scanned yet. Press s to measure folder sizes (du can take several minutes).")

    def action_scan(self) -> None:
        if self.scanning:
            self.notify(f"Already scanning {self.scanning}")
            return
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
            self._set_status(Text(error or "Scan failed.", style="#E06C75"))

    def _tick(self) -> None:
        if self.scanning and self.scanning == self.path:
            elapsed = int(time.time() - self.scan_started)
            self._set_status(f"{self.path}\nScanning with du… {elapsed}s (large folders can take minutes)")

    def _render_scan(self, scan: StorageScan) -> None:
        table = self.query_one("#storage-table", Table)
        table.clear()
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
        self._set_status(
            f"{scan.path}   {human_bytes(scan.total_bytes)} total · "
            f"scanned {format_age(scan.scanned_at)}{note}"
        )

    def _set_status(self, text) -> None:
        self.query_one("#storage-path", Static).update(text)

    def on_data_table_row_selected(self, event: Table.RowSelected) -> None:
        event.stop()
        # Only folder rows have a key (the "(files)" row has none).
        path = event.row_key.value
        if path and path != self.path:
            self._show_path(path, scan_if_missing=True)

    def check_action(self, action: str, parameters) -> Optional[bool]:
        if action == "up":
            return self.path != self.root
        return True

    def action_up(self) -> None:
        if self.path != self.root:
            self._show_path(os.path.dirname(self.path), scan_if_missing=False)
            self.refresh_bindings()

    def main_widget(self) -> Table:
        return self.query_one("#storage-table", Table)
