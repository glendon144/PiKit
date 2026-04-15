#!/usr/bin/env python3
import curses
from curses import wrapper

from ecm import ECMConfig, BoundaryLevel  # assuming ecm.py is in same directory


# Names, order, and display formatting for the sliders.
SLIDERS = [
    ("warmth",       "Warmth"),
    ("directness",   "Directness"),
    ("agreement",    "Agreement"),
    ("formality",    "Formality"),
]

BOUNDARY_OPTIONS = [
    BoundaryLevel.LOW,
    BoundaryLevel.MEDIUM,
    BoundaryLevel.HIGH,
]


def draw_slider(stdscr, y, x, label, value, active):
    """
    Draw one horizontal slider.

    value is [0.0, 1.0].
    """
    bar_width = 20
    filled = int(value * bar_width)
    empty = bar_width - filled

    if active:
        stdscr.attron(curses.A_REVERSE)

    stdscr.addstr(y,   x, f"{label:<12}")
    stdscr.addstr(y+1, x, "[" + ("█" * filled) + (" " * empty) + "]")
    stdscr.addstr(y+2, x, f" {int(value * 100):3d}% ")

    if active:
        stdscr.attroff(curses.A_REVERSE)

def draw_boundary_slider(stdscr, y, x, level: BoundaryLevel, active):
    """
    Draw a 3-position slider for the Boundaries setting.
    LOW → left, MEDIUM → center, HIGH → right.
    """
    labels = ["LOW", "MED", "HIGH"]
    positions = {BoundaryLevel.LOW: 0,
                 BoundaryLevel.MEDIUM: 1,
                 BoundaryLevel.HIGH: 2}

    idx = positions[level]
    bar_width = 20

    # Compute slider handle location (left, center, right)
    handle_positions = [
        1,
        bar_width // 2,
        bar_width - 2
    ]

    if active:
        stdscr.attron(curses.A_REVERSE)

    stdscr.addstr(y,   x, "Boundaries")

    # Draw bar
    stdscr.addstr(y+1, x, "[" + (" " * bar_width) + "]")

    # Draw handle
    handle_x = x + 1 + handle_positions[idx]
    stdscr.addstr(y+1, handle_x, "█")

    # Label underneath
    stdscr.addstr(y+2, x, f"{labels[idx]:<6}")

    if active:
        stdscr.attroff(curses.A_REVERSE)


def mixer_ui(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)

    cfg = ECMConfig()

    # selected = which control is active (0..len(SLIDERS) for sliders,
    # last index for boundaries)
    selected = 0
    total_controls = len(SLIDERS) + 1  # sliders + boundary selector

    while True:
        stdscr.clear()

        stdscr.addstr(0, 2, "Emotional Context Module — Mixer Prototype")
        stdscr.addstr(
            1,
            2,
            "Use ↑/↓ to select control, ←/→ to adjust, S = save, Q = quit",
        )

        # Draw sliders
        y = 3
        x = 4
        for idx, (attr, label) in enumerate(SLIDERS):
            val = getattr(cfg, attr)
            active = (idx == selected)
            draw_slider(stdscr, y, x, label, val, active)
            y += 4

        # Draw boundary slider
        boundary_index = total_controls - 1
        active = (selected == boundary_index)
        draw_boundary_slider(stdscr, y, x, cfg.boundaries, active)


        stdscr.refresh()

        ch = stdscr.getch()

        if ch in (ord("q"), ord("Q")):
            break

        # UP/DOWN: move between controls vertically
        if ch in (curses.KEY_UP, curses.KEY_DOWN):
            if ch == curses.KEY_DOWN:
                selected = (selected + 1) % total_controls
            else:  # KEY_UP
                selected = (selected - 1) % total_controls

        # LEFT/RIGHT: adjust current control’s value
        elif ch in (curses.KEY_LEFT, curses.KEY_RIGHT):
            if selected < len(SLIDERS):
                # Modify a numeric slider
                attr, _ = SLIDERS[selected]
                val = getattr(cfg, attr)
                delta = 0.05 if ch == curses.KEY_RIGHT else -0.05
                val = max(0.0, min(1.0, val + delta))
                setattr(cfg, attr, val)
            else:
                # Boundaries selector: cycle through LOW/MEDIUM/HIGH
                idx = BOUNDARY_OPTIONS.index(cfg.boundaries)
                if ch == curses.KEY_RIGHT:
                    idx = min(len(BOUNDARY_OPTIONS) - 1, idx + 1)
                else:
                    idx = max(0, idx - 1)
                cfg.boundaries = BOUNDARY_OPTIONS[idx]

        elif ch in (ord("s"), ord("S")):
            cfg.save_json("ecm_settings.json")
            stdscr.addstr(20, 4, "Settings saved to ecm_settings.json")
            stdscr.refresh()
            curses.napms(700)

    return cfg


def main():
    cfg = wrapper(mixer_ui)
    print("\nFinal ECM settings:\n", cfg.to_dict())


if __name__ == "__main__":
    main()

