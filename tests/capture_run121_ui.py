from __future__ import annotations

import argparse
import base64
import os
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.edge.options import Options


def edge_binary() -> str | None:
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    return str(next((p for p in candidates if p.is_file()), "")) or None


def capture(driver, url: str, path: Path, width: int, height: int) -> None:
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
        "width": width,
        "height": height,
        "deviceScaleFactor": 1,
        "mobile": width <= 430,
        "screenWidth": width,
        "screenHeight": height,
    })
    driver.get(url)
    deadline = time.time() + 20
    while time.time() < deadline:
        ready = driver.execute_script("return document.readyState")
        marker = driver.execute_script("return !!document.querySelector('[data-feature=\"zerocut-premium-editor-run121\"]')")
        if ready == "complete" and marker:
            break
        time.sleep(0.2)
    time.sleep(0.5)
    metrics = driver.execute_script(
        "return {innerWidth:window.innerWidth, scrollWidth:document.documentElement.scrollWidth,"
        "innerHeight:window.innerHeight, title:document.title}"
    )
    if metrics["innerWidth"] != width:
        raise RuntimeError(f"VIEWPORT_WIDTH_MISMATCH:{metrics}")
    if metrics["scrollWidth"] > width + 1:
        raise RuntimeError(f"HORIZONTAL_OVERFLOW:{metrics}")
    shot = driver.execute_cdp_cmd("Page.captureScreenshot", {
        "format": "png",
        "fromSurface": True,
        "captureBeyondViewport": False,
    })
    raw = base64.b64decode(shot["data"])
    if len(raw) < 10000:
        raise RuntimeError(f"SCREENSHOT_TOO_SMALL:{path}:{len(raw)}")
    path.write_bytes(raw)
    print(f"ZEROCUT_UI_CAPTURE={path.name} VIEWPORT={width}x{height} BYTES={len(raw)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-features=EdgeFirstRunExperience")
    binary = edge_binary()
    if binary:
        options.binary_location = binary

    driver = webdriver.Edge(options=options)
    try:
        capture(driver, args.url, out / "zerocut-desktop-1440.png", 1440, 1000)
        capture(driver, args.url, out / "zerocut-mobile-390.png", 390, 844)
        capture(driver, args.url, out / "zerocut-mobile-430.png", 430, 932)
    finally:
        driver.quit()

    print("ZEROCUT_RUN121_SCREENSHOTS=PASS")


if __name__ == "__main__":
    main()
