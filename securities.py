import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

periods = [
    ("1 Day",    -1.51),
    ("1 Week",   -2.00),
    ("1 Month",  -4.75),
    ("3 Months", -6.16),
    ("1 Year",   14.80),
]

labels = [p[0] for p in periods]
values = [p[1] for p in periods]
max_abs = max(abs(v) for v in values)

COLOR_POS = "#22c98e"
COLOR_NEG = "#f0454a"
BG        = "#0c0c0f"
TRACK     = "#141418"
GRID_LINE = "#2a2a2e"
TEXT_MAIN = "#f0f0f0"
TEXT_DIM  = "#bbbbbb"
TEXT_HINT = "#444444"

fig, ax = plt.subplots(figsize=(8, 5))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

ROW_STEP   = 0.84
y_positions = np.arange(len(periods)) * ROW_STEP
bar_height  = 0.56

# Draw track (background bar) for each row
for y in y_positions:
    ax.barh(y, max_abs * 2, left=-max_abs, height=bar_height,
            color=TRACK, zorder=1)

# Draw center zero line
ax.axvline(0, color=GRID_LINE, linewidth=1.2, zorder=2)

# Draw value bars
for i, (label, val) in enumerate(periods):
    color = COLOR_POS if val >= 0 else COLOR_NEG
    left  = 0 if val >= 0 else val
    ax.barh(y_positions[i], abs(val), left=left, height=bar_height,
            color=color, alpha=0.85, zorder=3)

# Period labels (left side)
for i, (label, val) in enumerate(periods):
    ax.text(-max_abs - 0.6, y_positions[i], label,
            ha="right", va="center",
            color=TEXT_DIM, fontsize=11, fontfamily="sans-serif")

# Value labels (right side)
for i, (label, val) in enumerate(periods):
    color = COLOR_POS if val >= 0 else COLOR_NEG
    sign  = "+" if val >= 0 else ""
    ax.text(max_abs + 0.6, y_positions[i], f"{sign}{val:.2f}%",
            ha="left", va="center",
            color=color, fontsize=11, fontweight="bold", fontfamily="sans-serif")

# Scale ticks at bottom
for x_tick in [-max_abs, -max_abs/2, 0, max_abs/2, max_abs]:
    sign = "+" if x_tick > 0 else ""
    label = "0" if x_tick == 0 else f"{sign}{x_tick:.0f}%"
    ax.text(x_tick, -0.50, label,
            ha="center", va="top",
            color=TEXT_HINT, fontsize=8, fontfamily="sans-serif")

# Header
fig.text(0.13, 0.902, "S&P 500",
         color=TEXT_MAIN, fontsize=34, fontweight="bold", fontfamily="serif",
         va="center")
fig.text(0.93, 0.908, "20/03/2026",
         color="#555555", fontsize=14, fontfamily="sans-serif",
         ha="right", va="bottom")
fig.text(0.93, 0.852, "Current price 6,506.48",
         color="#555555", fontsize=14, fontfamily="sans-serif",
         ha="right", va="bottom")

# Clean up axes
ax.set_xlim(-max_abs - 5, max_abs + 5)
ax.set_ylim(-0.8, y_positions[-1] + 0.45)
ax.axis("off")

plt.tight_layout(rect=[0.0, 0.02, 1.0, 0.84])
plt.savefig("chart.png",
            dpi=180, bbox_inches="tight", pad_inches=0.16, facecolor=BG)
print("Saved.")
