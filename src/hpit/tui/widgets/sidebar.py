from typing import List, Tuple

from textual.binding import Binding
from textual.widgets import Label, ListItem, ListView


class Sidebar(ListView):
    BINDINGS = [
        Binding("up", "cursor_up", "Navigate", key_display="↑↓"),
        Binding("down", "cursor_down", "Navigate", show=False),
        Binding("enter", "select_cursor", "Open"),
    ]

    def __init__(self, pages: List[Tuple[str, str]]):
        self.pages = pages
        super().__init__(
            *(
                ListItem(Label(self._label(title, i == 0)), id=f"nav-{page_id}")
                for i, (page_id, title) in enumerate(pages)
            ),
            id="sidebar",
        )
        self.border_title = "HPIT"

    def mark_active(self, active_id: str) -> None:
        for page_id, title in self.pages:
            label = self.query_one(f"#nav-{page_id} Label", Label)
            label.update(self._label(title, page_id == active_id))

    @staticmethod
    def _label(title: str, active: bool) -> str:
        return f"{'◉' if active else '○'} {title}"
