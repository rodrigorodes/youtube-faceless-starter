"""Capturas Chromium somente leitura: telas restantes do protótipo × app local."""
import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from compare_visual_reference import REFERENCE, ROOT, credentials  # noqa: E402

SCREENS = {  # nome: (rota do protótipo, rota do app)
    "ideas": ("#/ideas", "/studio/panel/tendencias"),
    "analytics": ("#/analytics", "/studio/panel/analytics"),
    "library": ("#/library", "/studio/panel/estilos"),
    "team": ("#/settings", "/studio/panel/equipe"),
    "connections": ("#/settings", "/studio/panel/conexoes"),
}

ap = argparse.ArgumentParser()
ap.add_argument("--output", required=True)
ap.add_argument("--only", default="")
args = ap.parse_args()
out = ROOT / args.output
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 1000}, http_credentials=credentials())
    for name, (ref_route, app_route) in SCREENS.items():
        if args.only and name != args.only:
            continue
        a = ctx.new_page()
        a.goto("http://127.0.0.1:8000" + app_route, wait_until="networkidle")
        a.screenshot(path=str(out / f"app-{name}.png"), full_page=True)
        r = ctx.new_page()
        r.goto(REFERENCE.as_uri() + ref_route, wait_until="networkidle")
        r.wait_for_timeout(300)
        r.screenshot(path=str(out / f"reference-{name}.png"), full_page=True)
print("ok")
