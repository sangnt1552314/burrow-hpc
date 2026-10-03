import calendar
from datetime import date, timedelta
from typing import Optional, Tuple

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from hpit.core.accounting import month_bounds, shift_month
from hpit.tui.theme import MUTED

DateRange = Tuple[date, date]


class CalendarScreen(ModalScreen):
    """Pick a date range: Enter on a start day, then on an end day.

    Returns (start, end), or None when cancelled.
    """

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
        Binding("left", "move(-1)", show=False),
        Binding("right", "move(1)", show=False),
        Binding("up", "move(-7)", show=False),
        Binding("down", "move(7)", show=False),
        Binding("left_square_bracket,pageup", "month(-1)", show=False),
        Binding("right_square_bracket,pagedown", "month(1)", show=False),
        Binding("enter,space", "pick", show=False),
        Binding("m", "whole_month", show=False),
        Binding("t", "this_month", show=False),
    ]

    def __init__(self, start: date, end: date):
        super().__init__()
        self.cursor = start
        self.start: Optional[date] = None  # Set after the first Enter.
        self.current = (start, end)

    def compose(self) -> ComposeResult:
        with Vertical(id="calendar", classes="panel") as panel:
            panel.border_title = "Usage period"
            yield Static(id="calendar-grid")
            yield Static(id="calendar-help", classes="message")

    def on_mount(self) -> None:
        self._redraw()

    def _redraw(self) -> None:
        if self.start is None:
            low, high = self.current
        else:
            low, high = sorted((self.start, self.cursor))

        text = Text(justify="center")
        text.append("◀  ", style=MUTED)
        text.append(self.cursor.strftime("%B %Y"), style="bold #61AFEF")
        text.append("  ▶\n\n", style=MUTED)
        text.append(" Mo  Tu  We  Th  Fr  Sa  Su\n", style=MUTED)

        today = date.today()
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(self.cursor.year, self.cursor.month)
        for week in weeks:
            for day in week:
                label = f" {day.day:>2} "
                if day.month != self.cursor.month or day > today:
                    style = "#3E4451"  # Other month, or future (no usage yet).
                elif day == self.cursor:
                    style = "bold #1E2127 on #61AFEF"
                elif low <= day <= high:
                    style = "#E6EDF3 on #2C3E55"
                elif day == today:
                    style = "bold #E5C07B"
                else:
                    style = ""
                text.append(label, style=style)
            text.append("\n")

        self.query_one("#calendar-grid", Static).update(text)

        help_text = Text()
        if self.start is None:
            help_text.append(f"Current: {self.current[0]} → {self.current[1]}\n", style="#E6EDF3")
            help_text.append("Enter: pick start day")
        else:
            help_text.append(f"Start: {self.start}\n", style="#E6EDF3")
            help_text.append("Enter: pick end day")
        help_text.append("   ←→↑↓ day   [ ] month\nm: whole month   t: this month   Esc: cancel")
        self.query_one("#calendar-help", Static).update(help_text)

    def action_move(self, days: int) -> None:
        self.cursor += timedelta(days=days)
        self._redraw()

    def action_month(self, months: int) -> None:
        target = shift_month(self.cursor, months)
        last_day = calendar.monthrange(target.year, target.month)[1]
        self.cursor = target.replace(day=min(self.cursor.day, last_day))
        self._redraw()

    def action_pick(self) -> None:
        if self.cursor > date.today():
            self.app.bell()  # No usage in the future.
            return
        if self.start is None:
            self.start = self.cursor
            self._redraw()
        else:
            self.dismiss(tuple(sorted((self.start, self.cursor))))

    def action_whole_month(self) -> None:
        if self.cursor.replace(day=1) > date.today():
            self.app.bell()
            return
        self.dismiss(month_bounds(self.cursor))

    def action_this_month(self) -> None:
        self.dismiss(month_bounds(date.today()))
