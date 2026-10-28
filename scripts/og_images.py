"""Render the link preview cards (_site/og/*.html, written by build_site.py) to 1200x630 PNGs.

    python scripts/og_images.py

Uses headless Chrome (preinstalled on GitHub's Ubuntu runners; Edge works locally on Windows).
A card that fails to render is skipped: the page still works, its shared link just shows no image.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OG = Path(__file__).resolve().parent.parent / "_site" / "og"
CANDIDATES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"]


def browser():
    for c in [os.environ.get("CHROME", "")] + CANDIDATES:
        if c and (shutil.which(c) or Path(c).exists()):
            return shutil.which(c) or c
    return None


def main():
    cards = sorted(OG.glob("*.html")) if OG.exists() else []
    exe = browser()
    if not cards or not exe:
        print(f"og: skipped ({len(cards)} cards, browser: {exe})")
        return
    profile = tempfile.mkdtemp()
    done = 0
    for card in cards:
        png = card.with_suffix(".png")
        cmd = [exe, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", f"--user-data-dir={profile}",
               "--window-size=1200,630", "--virtual-time-budget=4000", f"--screenshot={png}", card.as_uri()]
        try:
            subprocess.run(cmd, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            pass
        if png.exists():
            done += 1
        card.unlink()
    print(f"og: {done} of {len(cards)} preview images")
    if done < len(cards):
        sys.exit(0)


if __name__ == "__main__":
    main()
