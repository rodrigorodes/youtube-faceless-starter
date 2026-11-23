"""Read-only Chromium captures of the video workspace: prototype vs local app, every tab."""
import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from compare_visual_reference import REFERENCE, ROOT, credentials  # noqa: E402

TABS = ("cenas", "composicao", "qualidade", "publicacao", "fontes", "producao")
LABELS = {"cenas": "Cenas & Storyboard", "composicao": "Composição & Legendas",
          "qualidade": "Qualidade & Aprovação", "publicacao": "Publicação YouTube",
          "fontes": "Fontes & Evidências", "producao": "Produção"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--ref-video", default="")
    args = ap.parse_args()
    if args.base not in {"http://localhost:8000", "http://127.0.0.1:8000"}:
        raise ValueError("Only the local app is supported")
    out = ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": args.width, "height": 1000}, http_credentials=credentials())
        page = ctx.new_page()
        for tab in TABS:
            page.goto(f"{args.base}/studio/panel/videos/{args.video}/{tab}", wait_until="networkidle")
            page.screenshot(path=str(out / f"app-{tab}.png"), full_page=True)
        ref = ctx.new_page()
        ref.goto(REFERENCE.as_uri() + "#/videos", wait_until="networkidle")
        rows = ref.locator("tr.click")
        rows.nth(int(args.ref_video or 0)).click()
        for tab in TABS:
            if tab == "producao":  # no protótipo final não é aba: é o botão "Ver progresso / Diagnóstico"
                ref.locator('.head [data-a=tab][data-v=producao]').click()
            else:
                ref.locator("nav.tabs button.tab", has_text=LABELS[tab]).click()
            ref.wait_for_timeout(400)
            ref.screenshot(path=str(out / f"reference-{tab}.png"), full_page=True)
        browser.close()
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
