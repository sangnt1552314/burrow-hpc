from typing import Optional

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Static

from hpit.core import api
from hpit.core.cluster import submit_hint
from hpit.core.models import ClusterStatus
from hpit.tui.pages.base import Page
from hpit.tui.theme import MUTED
from hpit.tui.util import call_backend, usage_bar


class ClusterPage(Page):
    """Free GPUs and queue pressure (what `hpc gstat` shows)."""

    TITLE = "Cluster"

    BINDINGS = [Binding("f", "toggle_free", "Free only")]

    def __init__(self):
        super().__init__(id="cluster")
        self.status: Optional[ClusterStatus] = None
        self.free_only = False

    def compose(self) -> ComposeResult:
        yield Static("Loading…", id="cluster-summary", classes="box")
        yield Static("Where can my job start now?", classes="section-title")
        yield DataTable(id="placement-table", show_cursor=False)
        yield Static("Queues", classes="section-title")
        yield DataTable(id="queue-table", show_cursor=False)
        yield Static("Nodes", id="nodes-title", classes="section-title")
        yield DataTable(id="node-table", cursor_type="row")

    def on_mount(self) -> None:
        placements = self.query_one("#placement-table", DataTable)
        placements.add_columns("GPUs", "Queue", "Submit with", "Nodes with room now", "Waiting", "Limits")
        placements.can_focus = False
        queues = self.query_one("#queue-table", DataTable)
        queues.add_columns("Queue", "Running", "Waiting", "Users waiting")
        queues.can_focus = False
        self.query_one("#node-table", DataTable).add_columns(
            "Node", "State", "GPUs free", "Model", "Pool", "Only for", "CPUs free", "Memory free/total", "Jobs",
        )

    def load(self) -> None:
        self.load_status()

    @work(thread=True, exclusive=True, group="cluster")
    def load_status(self) -> None:
        status, error = call_backend(api.get_cluster_status)
        self.app.call_from_thread(self._show_status, status, error)

    def _show_status(self, status: Optional[ClusterStatus], error: Optional[str]) -> None:
        summary = self.query_one("#cluster-summary", Static)
        if status is None:
            summary.update(Text(error or "Cluster status unavailable.", style="#E06C75"))
            return
        self.status = status

        total = status.gpus_total or 1
        text = Text("Free GPUs you can use  ", style="bold")
        text.append(f"{status.my_gpus_free}", style="bold #98C379" if status.my_gpus_free else "bold #E06C75")
        text.append(f"   (whole cluster {status.gpus_free} / {status.gpus_total})   ", style=MUTED)
        text.append_text(usage_bar(status.gpus_free / total, 30, "#98C379"))
        offline = sum(1 for n in status.nodes if not n.available)
        note = f"   {offline} node(s) offline, not counted" if offline else ""
        text.append(note, style=MUTED)
        if status.queues_error:
            text.append(f"\nQueues: {status.queues_error}", style="#E5C07B")
        else:
            text.append(f"\nQueue snapshot from {status.queues_updated} (collected by the site every few minutes)", style=MUTED)
        summary.update(text)

        self._render_placements(status)

        queues = self.query_one("#queue-table", DataTable)
        queues.clear()
        for q in status.queues:
            name = Text(q.name, style="bold" if q.name == "auto" else "")
            queues.add_row(
                name,
                Text(str(q.running), justify="right", style="#98C379"),
                Text(str(q.waiting), justify="right", style="#E5C07B"),
                Text(str(q.users_waiting), justify="right"),
            )
        queues.styles.height = len(status.queues) + 1
        self._render_nodes()

    def _render_placements(self, status: ClusterStatus) -> None:
        table = self.query_one("#placement-table", DataTable)
        table.clear()
        for p in status.placements:
            if p.nodes:
                nodes = Text(", ".join(f"{n.name} ({n.gpus_free} {n.gpu_model})" for n in p.nodes[:3]), style="#98C379")
                if len(p.nodes) > 3:
                    nodes.append(f" +{len(p.nodes) - 3} more", style=MUTED)
            else:
                nodes = Text("none — the job would wait", style="#E5C07B")
            queue = Text(p.queue.name, style="bold" if p.queue.via != "auto" else "")
            if p.queue.via != "auto":
                queue.append(" (you're on its user list)", style=MUTED)
            table.add_row(
                Text(str(p.gpus), justify="right"),
                queue,
                Text(submit_hint(p), style="#E5C07B"),
                nodes,
                Text(str(p.waiting), justify="right", style="#E5C07B" if p.waiting else MUTED),
                Text(f"≤{p.queue.max_walltime} · {p.queue.max_run} running", style=MUTED),
            )
        table.styles.height = len(status.placements) + 2  # header + scrollbar

    def _render_nodes(self) -> None:
        if self.status is None:
            return
        table = self.query_one("#node-table", DataTable)
        table.clear()
        for n in self.status.nodes:
            if self.free_only and not (n.available and n.gpus_free):
                continue
            if not n.available:
                state = Text(n.state, style="#E06C75")
            elif n.gpus_free:
                state = Text(n.state, style="#98C379")
            else:
                state = Text(n.state, style=MUTED)
            # Offline nodes report their GPUs as "free"; grey them out.
            bar_color = "#98C379" if n.available else "#4B5263"
            gpus = usage_bar(n.gpus_free / n.gpus_total if n.gpus_total else 0, n.gpus_total or 8, bar_color)
            gpus.append(f" {n.gpus_free}/{n.gpus_total}", style="" if n.available else MUTED)
            table.add_row(
                n.name, state, gpus,
                Text(n.gpu_model, style=MUTED),
                Text(n.pool, style=MUTED),
                Text(n.dedicated_queue, style="#E5C07B") if n.dedicated_queue else Text("—", style=MUTED),
                Text(f"{n.cpus_free}/{n.cpus_total}", justify="right"),
                Text(n.mem, justify="right", style=MUTED),
                Text(str(n.jobs), justify="right"),
            )

    def action_toggle_free(self) -> None:
        self.free_only = not self.free_only
        self.query_one("#nodes-title", Static).update(
            "Nodes with free GPUs" if self.free_only else "Nodes"
        )
        self._render_nodes()

    def main_widget(self) -> DataTable:
        return self.query_one("#node-table", DataTable)
