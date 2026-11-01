"""Draw the README's benchmark chart from results recorded by bench.py.

    uv run --with matplotlib bench/chart.py

Writes bench/chart-light.svg and bench/chart-dark.svg. The numbers are the fast
suite (5,000 modules, 2,000 test files, 20,000 tests); update them after
rerunning bench.py.
"""

from pathlib import Path

import matplotlib

matplotlib.use("svg")
import matplotlib.pyplot as plt

# (group, testy seconds, pytest seconds, pytest's label in that group)
RESULTS = [
    ("Full run,\none at a time", 1.01, 5.64, "pytest"),
    ("Full run,\nin parallel", 0.90, 9.42, "pytest -n auto"),
    ("After editing\none module", 0.33, 5.64, "pytest (reruns everything)"),
]

THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "text": "#0b0b0b",
        "muted": "#52514e",
        "grid": "#e6e5e1",
        "testy": "#2a78d6",
        "pytest": "#eb6834",
    },
    "dark": {
        "surface": "#1a1a19",
        "text": "#f0efec",
        "muted": "#c3c2b7",
        "grid": "#33332f",
        "testy": "#3987e5",
        "pytest": "#d95926",
    },
}


def draw(theme: dict, path: Path) -> None:
    plt.rcParams.update(
        {"font.family": "sans-serif", "font.size": 11, "svg.fonttype": "none"}
    )
    fig, ax = plt.subplots(figsize=(8, 3.6))
    fig.patch.set_facecolor(theme["surface"])
    ax.set_facecolor(theme["surface"])

    bar, gap = 0.34, 0.02
    for i, (_, testy, pytest, pytest_label) in enumerate(RESULTS):
        y = i * 1.0
        for offset, value, color, label in (
            (-(bar + gap) / 2, testy, theme["testy"], "testy"),
            ((bar + gap) / 2, pytest, theme["pytest"], pytest_label),
        ):
            ax.barh(y + offset, value, height=bar, color=color, linewidth=0)
            ax.text(
                value + 0.12,
                y + offset,
                f"{value:.2f}s  {label}",
                va="center",
                ha="left",
                color=theme["muted"],
                fontsize=10,
            )

    ax.set_yticks([i * 1.0 for i in range(len(RESULTS))])
    ax.set_yticklabels([group for group, *_ in RESULTS], color=theme["text"])
    ax.invert_yaxis()
    ax.set_xlim(0, 12.5)
    ax.set_xlabel("seconds (lower is better)", color=theme["muted"])
    ax.tick_params(axis="x", colors=theme["muted"])
    ax.tick_params(axis="y", length=0, pad=8)
    ax.grid(axis="x", color=theme["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(theme["grid"])

    fig.tight_layout()
    fig.savefig(path, facecolor=theme["surface"])
    plt.close(fig)


if __name__ == "__main__":
    here = Path(__file__).parent
    for name, theme in THEMES.items():
        draw(theme, here / f"chart-{name}.svg")
