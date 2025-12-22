#!/usr/bin/env python3
"""
Generate the Nostr Proxy logo.
Requires: pip install Pillow
"""
import math

from PIL import Image, ImageDraw

# Render at 4x size for antialiasing
scale = 4
size = 128 * scale
final_size = 128

dark_purple = (80, 40, 120)
light_purple = (140, 100, 180)
white = (255, 255, 255)
white_transparent = (255, 255, 255, 180)

margin = 4 * scale

swoosh_center = ((128 + 100) * scale, -90 * scale)
swoosh_radius = 220 * scale

# Create circular mask
mask = Image.new("L", (size, size), 0)
mask_draw = ImageDraw.Draw(mask)
mask_draw.ellipse([margin, margin, size - margin, size - margin], fill=255)

# Create background with swoosh
bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
bg_draw = ImageDraw.Draw(bg)
bg_draw.ellipse([margin, margin, size - margin, size - margin], fill=dark_purple)
bg_draw.ellipse(
    [
        swoosh_center[0] - swoosh_radius,
        swoosh_center[1] - swoosh_radius,
        swoosh_center[0] + swoosh_radius,
        swoosh_center[1] + swoosh_radius,
    ],
    fill=light_purple,
)

# Apply circular mask
final = Image.new("RGBA", (size, size), (0, 0, 0, 0))
final.paste(bg, mask=mask)
draw = ImageDraw.Draw(final)

center_x, center_y = size // 2, size // 2
radius = 44 * scale
angles = [-35, -12, 12, 35]
relay_positions = [
    (
        center_x + radius * math.cos(math.radians(a)),
        center_y + radius * math.sin(math.radians(a)),
    )
    for a in angles
]

for x, y in relay_positions:
    draw.line([(center_x, center_y), (x, y)], fill=white_transparent, width=2 * scale)

draw.ellipse(
    [
        center_x - 14 * scale,
        center_y - 14 * scale,
        center_x + 14 * scale,
        center_y + 14 * scale,
    ],
    fill=white,
)
draw.line(
    [(16 * scale, center_y), (center_x - 14 * scale, center_y)],
    fill=white,
    width=4 * scale,
)
draw.polygon(
    [
        (center_x - 14 * scale, center_y),
        (center_x - 22 * scale, center_y - 6 * scale),
        (center_x - 22 * scale, center_y + 6 * scale),
    ],
    fill=white,
)

for x, y in relay_positions:
    draw.ellipse(
        [x - 7 * scale, y - 7 * scale, x + 7 * scale, y + 7 * scale], fill=white
    )

# Downscale with LANCZOS for antialiasing
final = final.resize((final_size, final_size), Image.LANCZOS)

final.save("nostr-proxy.png")
print("Logo saved to nostr-proxy.png")
