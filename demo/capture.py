"""Capture demo screenshots of the running web app via headless Chrome.

Static pages are screenshotted directly. Interactive states (running timeline,
quality drawer, FDX output) are rendered by fetching the real page HTML,
inlining the stylesheet, setting the desired state, and screenshotting that
local file — so the visuals are the app's real markup/CSS, just frozen.
"""

from __future__ import annotations

import html as html_lib
import subprocess
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8123"
RID = "50836d629090"  # the real DeepSeek run (real scenes + 3 story findings)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H = 1280, 800
ROOT = Path(__file__).resolve().parent
SHOTS = ROOT / "shots"
TMP = ROOT / "_tmp"
SHOTS.mkdir(exist_ok=True)
TMP.mkdir(exist_ok=True)


def fetch(path: str) -> str:
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return r.read().decode("utf-8")


CSS = ""


def strip_dark_mode(css: str) -> str:
    """Remove the prefers-color-scheme: dark block so shots render in the
    on-brand light paper palette regardless of Chrome's emulated scheme."""
    marker = "@media (prefers-color-scheme: dark)"
    i = css.find(marker)
    if i == -1:
        return css
    brace = css.find("{", i)
    depth, j = 0, brace
    while j < len(css):
        if css[j] == "{":
            depth += 1
        elif css[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return css[:i] + css[j + 1 :]


def inline_css(page: str) -> str:
    # Disable entrance animations so the headless screenshot captures the
    # resting (full-opacity) state instead of a mid-fade frame.
    freeze = "*{animation:none !important;transition:none !important;}"
    return page.replace(
        '<link rel="stylesheet" href="/static/app.css" />',
        f"<style>\n{CSS}\n{freeze}\n</style>",
    )


def strip_scripts(page: str) -> str:
    while "<script>" in page and "</script>" in page:
        a = page.index("<script>")
        b = page.index("</script>") + len("</script>")
        page = page[:a] + page[b:]
    return page


def shoot(url_or_file: str, out: str) -> None:
    subprocess.run(
        [
            CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            f"--window-size={W},{H}",
            f"--screenshot={SHOTS / out}", url_or_file,
        ],
        check=True, capture_output=True,
    )
    print("shot:", out)


def write_local(name: str, content: str) -> str:
    p = TMP / name
    p.write_text(content, encoding="utf-8")
    return p.as_uri()


def main() -> None:
    global CSS
    for _ in range(40):
        try:
            urllib.request.urlopen(BASE + "/healthz", timeout=2).read()
            break
        except Exception:
            time.sleep(0.5)
    CSS = strip_dark_mode(fetch("/static/app.css"))

    # 1. Upload page (render locally so it uses the light palette)
    upload = strip_scripts(inline_css(fetch("/")))
    shoot(write_local("upload.html", upload), "1_upload.png")

    # 2. Running timeline — freeze a mid-run state
    run = strip_scripts(inline_css(fetch(f"/runs/{RID}/running")))
    done = {"parse": "选取 3 章（原著 3 章）", "analyze": "5 人物 · 5 地点", "outline": "5 场"}
    for stage, detail in done.items():
        run = run.replace(
            f'class="tl-node" data-stage="{stage}"',
            f'class="tl-node done" data-stage="{stage}"',
        )
        # fill the first empty detail span after this stage's label
    run = run.replace('class="tl-node" data-stage="generate"', 'class="tl-node done" data-stage="generate"')
    run = run.replace('class="tl-node" data-stage="draft"', 'class="tl-node active" data-stage="draft"')
    run = run.replace('id="run-elapsed">已用时 0.0s', 'id="run-elapsed">已用时 41.8s')
    # inject the draft progress detail
    run = run.replace(
        '<span class="tl-label">逐场扩写</span><span class="tl-detail"></span>',
        '<span class="tl-label">逐场扩写</span><span class="tl-detail">已扩写 3 / 5 场</span>',
    )
    shoot(write_local("running.html", run), "2_running.png")

    # 3. Result reader (default entities drawer) — real DeepSeek scenes
    reader = strip_scripts(inline_css(fetch(f"/runs/{RID}")))
    shoot(write_local("reader.html", reader), "3_reader.png")

    # 4. Quality drawer — flip to the quality panel (real story findings)
    res = fetch(f"/runs/{RID}")
    res = inline_css(res)
    res = res.replace('data-panel="entities">', 'data-panel="entities" hidden>')
    res = res.replace('data-panel="quality" hidden>', 'data-panel="quality">')
    res = res.replace('class="drawer-tab active" data-tab="entities"', 'class="drawer-tab" data-tab="entities"')
    res = res.replace('class="drawer-tab" data-tab="quality"', 'class="drawer-tab active" data-tab="quality"')
    res = strip_scripts(res)
    shoot(write_local("quality.html", res), "4_quality.png")

    # 5. Final Draft (.fdx) output — proof of pro-tool integration
    fdx = fetch(f"/runs/{RID}/download/fdx")
    snippet = "\n".join(fdx.splitlines()[:34])
    page = f"""<!doctype html><meta charset=utf-8><style>
    body{{margin:0;background:#1f1b16;color:#ece6d8;font-family:'SF Mono',Menlo,monospace;}}
    .bar{{background:#2a251d;color:#b7892b;padding:14px 22px;font-size:15px;border-bottom:1px solid #3a352c;}}
    .bar b{{color:#d4564a;}} pre{{padding:20px 24px;font-size:14px;line-height:1.5;white-space:pre-wrap;}}
    </style><div class=bar><b>screenplay.fdx</b> · Final Draft · 可直接在 Final Draft / WriterDuet / Fade In 打开</div>
    <pre>{html_lib.escape(snippet)}</pre>"""
    shoot(write_local("fdx.html", page), "5_fdx.png")

    # 6. History page
    history = strip_scripts(inline_css(fetch("/history")))
    shoot(write_local("history.html", history), "6_history.png")


if __name__ == "__main__":
    main()
