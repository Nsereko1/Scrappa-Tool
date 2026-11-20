# core/images.py
"""
Image URL resolution.
- If the adapter provides `image_url`, use it.
- Otherwise, generate a deterministic placeholder from the title.
"""

import hashlib
import urllib.parse

_PALETTE = [
    "1f77b4", "ff7f0e", "2ca02c", "d62728", "9467bd",
    "8c564b", "e377c2", "17becf", "bcbd22", "7f7f7f",
]


def hue_to_hex(hue):
    return _PALETTE[hue % len(_PALETTE)]


def resolve_image(item):
    if item.get("image_url"):
        return item["image_url"]
    title = item.get("title") or "product"
    platform = item.get("platform") or "unknown"
    h = int(hashlib.md5(f"{platform}:{title}".encode()).hexdigest()[:6], 16)
    hue = h % 360
    initial = (title.strip()[0] if title.strip() else "?").upper()
    return (
        f"https://placehold.co/120x120/{hue_to_hex(hue)}/ffffff"
        f"?text={urllib.parse.quote(initial)}&font=roboto"
    )
