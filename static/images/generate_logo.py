#!/usr/bin/env python3
"""
Generate the Nostr Proxy logo.
Requires: pip install Pillow
"""
import math

from PIL import Image, ImageDraw  # type: ignore[import-not-found]

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

# Central circle (the multiplexer)
draw.ellipse(
    [
        center_x - 14 * scale,
        center_y - 14 * scale,
        center_x + 14 * scale,
        center_y + 14 * scale,
    ],
    fill=white,
)

# Bi-directional arrow
arrow_head_size = 8 * scale
left_tip = 10 * scale  # leftmost point of left arrow
right_tip = center_x - 14 * scale  # rightmost point (touching circle)

# Arrow shaft - between the two arrow heads (not extending into them)
shaft_left = left_tip + arrow_head_size
shaft_right = right_tip - arrow_head_size
draw.line([(shaft_left, center_y), (shaft_right, center_y)], fill=white, width=4 * scale)

# Right-pointing arrow head (going into circle) - tip touches circle
draw.polygon(
    [
        (right_tip, center_y),
        (right_tip - arrow_head_size, center_y - 6 * scale),
        (right_tip - arrow_head_size, center_y + 6 * scale),
    ],
    fill=white,
)

# Left-pointing arrow head (coming out) - tip at left edge
draw.polygon(
    [
        (left_tip, center_y),
        (left_tip + arrow_head_size, center_y - 6 * scale),
        (left_tip + arrow_head_size, center_y + 6 * scale),
    ],
    fill=white,
)

# Draw output circles on top
for x, y in relay_positions:
    draw.ellipse(
        [x - 7 * scale, y - 7 * scale, x + 7 * scale, y + 7 * scale], fill=white
    )

# Downscale with LANCZOS for antialiasing
final = final.resize((final_size, final_size), Image.LANCZOS)

final.save("nostr-proxy.png")
print("Logo saved to nostr-proxy.png")
