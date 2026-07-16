"""Parse human tap coords and optional click-on-image picker."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# TODO scrcpy: hook click-mirror stream later for live device tap capture.


def parse_coord_input(
    raw: str,
    *,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int, float, float] | None:
    """Parse '1234,5678' | '0.92,0.52' | '92% 52%' → (x, y, x_frac, y_frac)."""
    text = (raw or "").strip().lower().replace(",", " ")
    if not text:
        return None
    # Percent form: 92% 52% or 92%52%
    pct = re.findall(r"([0-9]*\.?[0-9]+)\s*%", text)
    if len(pct) >= 2:
        xf = float(pct[0]) / 100.0
        yf = float(pct[1]) / 100.0
        if not (0.0 <= xf <= 1.0 and 0.0 <= yf <= 1.0):
            return None
        x = max(1, min(screen_width - 1, int(round(xf * screen_width))))
        y = max(1, min(screen_height - 1, int(round(yf * screen_height))))
        return x, y, xf, yf

    nums = re.findall(r"[0-9]*\.?[0-9]+", text)
    if len(nums) < 2:
        return None
    a, b = float(nums[0]), float(nums[1])
    # Fraction if both in (0,1]
    if 0.0 < a <= 1.0 and 0.0 < b <= 1.0 and screen_width > 0 and screen_height > 0:
        xf, yf = a, b
        x = max(1, min(screen_width - 1, int(round(xf * screen_width))))
        y = max(1, min(screen_height - 1, int(round(yf * screen_height))))
        return x, y, xf, yf
    # Absolute pixels
    x, y = int(round(a)), int(round(b))
    if x <= 0 or y <= 0:
        return None
    xf = x / screen_width if screen_width else 0.0
    yf = y / screen_height if screen_height else 0.0
    return x, y, xf, yf


def pick_point_on_image(
    image_path: Path | str,
    device_w: int,
    device_h: int,
) -> tuple[int, int, float, float] | None:
    """Show before PNG in a tkinter window; click records device-scaled coords.

    Returns None if tkinter/PIL unavailable or user closes without clicking.
    """
    path = Path(image_path)
    if not path.is_file() or device_w <= 0 or device_h <= 0:
        return None
    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except ImportError:
        return None

    result: dict[str, tuple[int, int, float, float] | None] = {"point": None}

    root = tk.Tk()
    root.title("Teach: click the comments icon (then close)")
    img = Image.open(path)
    img_w, img_h = img.size
    # Fit to ~900px tall max for usability
    max_h = 900
    scale = min(1.0, max_h / img_h) if img_h else 1.0
    disp_w = max(1, int(img_w * scale))
    disp_h = max(1, int(img_h * scale))
    if scale < 1.0:
        img = img.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
    photo = ImageTk.PhotoImage(img)

    label = tk.Label(root, image=photo)
    label.pack()
    hint = tk.Label(root, text="Click the target on the BEFORE screenshot")
    hint.pack()

    def on_click(event: tk.Event) -> None:  # type: ignore[name-defined]
        # Map display click → image pixel → device pixel
        ix = event.x / disp_w * img_w if disp_w else 0
        iy = event.y / disp_h * img_h if disp_h else 0
        # Screenshot may match device size; scale to wm_size if different
        x = int(round(ix / img_w * device_w)) if img_w else 0
        y = int(round(iy / img_h * device_h)) if img_h else 0
        x = max(1, min(device_w - 1, x))
        y = max(1, min(device_h - 1, y))
        xf = x / device_w
        yf = y / device_h
        result["point"] = (x, y, xf, yf)
        hint.config(text=f"Recorded ({x}, {y}) — close window to continue")

    label.bind("<Button-1>", on_click)
    root.mainloop()
    return result["point"]
