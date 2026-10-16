#!/usr/bin/env python3
"""Plot the breakdown of how unpinned local MCP servers are unpinned.

Reads data/2026-10/stats.json and writes charts/mcp-pinning.png.
Matches the visual style of scripts/charts.py.
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Paths relative to repo root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATS_PATH = os.path.join(ROOT, "data", "2026-10", "stats.json")
OUT_PATH = os.path.join(ROOT, "charts", "mcp-pinning.png")

with open(STATS_PATH) as f:
    S = json.load(f)

SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "text.color": INK,
    "axes.labelcolor": INK2,
    "xtick.color": INK2,
    "ytick.color": INK,
    "axes.edgecolor": GRID,
})

def frac(s):
    a, b = s.split(" ")[0].split("/")
    return int(a), int(b)

def base(ax, fig):
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(length=0)
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)

def foot(fig, t):
    fig.text(0.01, 0.015, t, fontsize=8.5, color=INK2, ha="left")

# Three overlapping groups of the 346 repos with a local (stdio) MCP server
items = [
    ("npm package via npx, no exact version (SSG401)", S["unpinned_mcp_npm"], BLUE),
    ("Python package with no version (SSG402)", S["unpinned_mcp_py"], ORANGE),
    ("asks for latest (SSG403)", S["unpinned_mcp_latest"], AQUA),
]

fig, ax = plt.subplots(figsize=(10, 3.8))
base(ax, fig)

labels = [i[0] for i in items][::-1]
vals = []
dens = []
for name, s, _col in items[::-1]:
    a, b = frac(s)
    vals.append(100 * a / b)
    dens.append((a, b))

colors = [i[2] for i in items][::-1]
ax.barh(labels, vals, color=colors, height=0.55)
for y, (v, (a, b)) in enumerate(zip(vals, dens)):
    ax.text(v + 0.8, y, f"{v:.1f}%  ({a:,} of {b:,})", va="center", fontsize=10, color=INK)

ax.set_xlim(0, 40)
ax.set_xticks([0, 10, 20, 30, 40])
ax.set_xticklabels(["0%", "10%", "20%", "30%", "40%"])
ax.set_title("How unpinned local MCP servers are unpinned", loc="left", fontsize=14, fontweight="bold", pad=12)

denom = S["repos_with_stdio_mcp"]
foot(
    fig,
    f"Of the {denom:,} repositories with a local MCP server. Groups overlap "
    f"(total unpinned is {frac(S['unpinned_mcp'])[0]}).\n"
    f"Sample of 2,999 public GitHub repositories, collected 13 Oct 2026. "
    f"Source: data/2026-10/stats.json.",
)

fig.tight_layout(rect=(0, 0.10, 1, 1))
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
fig.savefig(OUT_PATH, dpi=200)
plt.close(fig)
print(f"wrote {OUT_PATH}")
