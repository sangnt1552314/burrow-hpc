from typing import List, Optional

from textual.containers import Vertical
from textual.widget import Widget

from hpit.core.models import Job


class Page(Vertical):
    """One sidebar destination, shown in the content area.

    The App fetches jobs once and hands them to every page via
    `show_jobs`; pages load anything else themselves in `load`.
    """

    TITLE = ""

    def __init__(self, **kwargs):
        super().__init__(classes="page panel", **kwargs)
        self.border_title = self.TITLE
        self._loaded = False

    def on_show(self) -> None:
        # Load lazily the first time the page is opened.
        if not self._loaded:
            self._loaded = True
            self.load()

    def load(self) -> None:
        """Fetch page data (non-blocking). Also called on refresh."""

    def refresh_page(self) -> None:
        if self._loaded:
            self.load()

    def show_jobs(self, jobs: List[Job], error: Optional[str]) -> None:
        """Receive the shared job list (or an error) from the App."""

    def main_widget(self) -> Optional[Widget]:
        """The widget that gets focus when the page is opened."""
        return None
