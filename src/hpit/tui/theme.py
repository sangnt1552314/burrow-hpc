from textual.theme import Theme

# A dark, blue-accented theme (One Dark palette).
HPIT_THEME = Theme(
    name="hpit",
    primary="#61AFEF",
    secondary="#56B6C2",
    accent="#61AFEF",
    warning="#E5C07B",
    error="#E06C75",
    success="#98C379",
    foreground="#ABB2BF",
    background="#1E2127",
    surface="#21252B",
    panel="#2C313A",
    dark=True,
    variables={
        "footer-background": "#1E2127",
        "footer-key-foreground": "#61AFEF",
        "footer-description-foreground": "#7F848E",
        "block-cursor-background": "#2C3E55",
        "block-cursor-foreground": "#E6EDF3",
        "block-cursor-text-style": "none",
        "block-cursor-blurred-background": "#2C313A",
        "block-cursor-blurred-foreground": "#ABB2BF",
        "block-cursor-blurred-text-style": "none",
        "block-hover-background": "#262A31",
        "scrollbar": "#3A3F4B",
        "scrollbar-hover": "#4B5263",
        "scrollbar-active": "#61AFEF",
        "scrollbar-background": "#1E2127",
        "scrollbar-background-hover": "#1E2127",
        "scrollbar-background-active": "#1E2127",
        "input-cursor-background": "#61AFEF",
    },
)

# Colours for job states, shared by every table that shows jobs.
STATE_STYLES = {
    "R": ("●", "#98C379"),
    "Q": ("◌", "#E5C07B"),
    "H": ("◍", "#D19A66"),
    "E": ("●", "#61AFEF"),
    "F": ("✓", "#7F848E"),
    "S": ("◍", "#D19A66"),
}

MUTED = "#7F848E"
