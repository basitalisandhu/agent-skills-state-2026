"""Draw charts/trend.png from data/trend.csv: one line per key finding, one point per month.

Usage: python scripts/plot_trend.py [TREND_CSV] [OUT_PNG]
With a single month the chart shows one point per finding; the lines appear from the second month.
"""
import csv
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = [
    ("No SECURITY.md (all repositories)", "no_security_md_pct", "#2a78d6"),
    ("Stdio MCP server not pinned", "unpinned_mcp_pct", "#eb6834"),
    ("No licence file (all repositories)", "no_licence_file_pct", "#1baf7a"),
    ("A skill allows unrestricted Bash", "unrestricted_bash_repos_pct", "#8f5bd6"),
    ("A SKILL.md fails YAML parsing", "yaml_reject_repos_pct", "#c9a227"),
]


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "trend.csv")
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "charts", "trend.png")
    rows = sorted(csv.DictReader(open(src, newline="", encoding="utf-8")), key=lambda r: r["month"])
    if not rows:
        print("no months in", src)
        return 0
    months = [r["month"] for r in rows]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.color": INK, "axes.labelcolor": INK2,
                         "xtick.color": INK2, "ytick.color": INK, "axes.edgecolor": GRID})
    fig, ax = plt.subplots(figsize=(10, 5.6))
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(length=0)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    xs = list(range(len(months)))
    for label, key, colour in SERIES:
        ys = [float(r[key]) for r in rows]
        ax.plot(xs, ys, color=colour, lw=2, marker="o", ms=6, label=label)
        ax.text(xs[-1] + 0.08, ys[-1], f"{ys[-1]:.1f}%", va="center", fontsize=9.5, color=colour)
    ax.set_xticks(xs)
    ax.set_xticklabels(months)
    ax.set_xlim(-0.5, max(1, len(xs) - 1) + 0.6)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.legend(frameon=False, loc="upper center", ncol=3, bbox_to_anchor=(0.5, -0.08), fontsize=9.5)
    ax.set_title("Key findings by month", loc="left", fontsize=14, fontweight="bold", pad=12)
    note = ("One new random sample of up to 3,000 repositories each month. Precision was measured in October 2026 only."
            if len(rows) > 1 else "First edition only (October 2026); the trend line starts with the next monthly run.")
    fig.text(0.01, 0.015, note, fontsize=8.5, color=INK2, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    fig.savefig(dst, dpi=200)
    print(f"wrote {dst} ({len(rows)} month{'s' if len(rows) != 1 else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
