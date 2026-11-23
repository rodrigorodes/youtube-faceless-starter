"""Diff de estilos computados, componente a componente: protótipo × app local (somente leitura)."""
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from compare_visual_reference import REFERENCE, ROOT, credentials  # noqa: E402

PROPS = ["fontFamily", "fontSize", "fontWeight", "lineHeight", "letterSpacing", "color", "backgroundColor",
         "borderTopWidth", "borderTopColor", "borderTopStyle", "borderTopLeftRadius", "paddingTop", "paddingRight",
         "paddingBottom", "paddingLeft", "marginTop", "marginBottom", "display", "gap", "textTransform", "boxShadow",
         "width", "height"]
JS = """([sels, props]) => Object.fromEntries(sels.map(([key, ref, app]) => {
  const out = [];
  document.querySelectorAll(window.__SIDE === 'ref' ? ref : app).forEach((el, i) => {
    if (i > 2) return; const s = getComputedStyle(el), r = el.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const o = {text: (el.textContent || '').trim().slice(0, 30)};
    props.forEach(p => o[p] = s[p]); o.width = Math.round(r.width) + 'px'; o.height = Math.round(r.height) + 'px';
    out.push(o);
  });
  return [key, out];
}))"""
SELS = [
    ["h1", ".head h1", "h1"], ["eyebrow", ".head .eyebrow", ".head .eyebrow"], ["pill", ".head .pill", ".head .pill"],
    ["tab", ".tabs .tab", ".abas-video a"], ["card", ".two .card", ".two .card"], ["card h3", ".two .card h3", ".two .card h3"],
    ["btn", ".btn", "main .btn, .pagina .btn"], ["btn.small", ".btn.small", ".pagina .btn.small"],
    ["btn.primary", ".btn.primary", ".pagina .btn.primary"], ["btn.ok", ".btn.ok", ".pagina .btn.ok"],
    ["btn.ghost", ".btn.ghost", ".pagina .btn.ghost"], ["lbl", ".field label, .lbl", ".pagina .field label, .pagina .lbl"],
    ["input", ".content input[type=text], .content input[type=number]", ".pagina input[type=text], .pagina input[type=number]"],
    ["select", ".content select", ".pagina select"], ["textarea", ".content textarea", ".pagina textarea"],
    ["note", ".note", ".pagina .note"], ["sub", ".sub", ".pagina .sub"], ["sample", ".sample", ".pagina .sample"],
    ["thumb", ".thumb", ".thumb"], ["scene", ".scene", ".scene"], ["player", ".player", ".player"], ["dock", ".dock", ".dock"],
    ["frame", ".frame", ".frame"], ["track", ".track", ".track"], ["summary", "details.diag summary", "details.diag summary"],
    ["step", ".step", ".step"], ["gate", ".gate", ".gate"], ["seg", ".seg", ".seg"], ["tog", ".tog", ".tog"],
]


def collect(page, side):
    page.evaluate(f"window.__SIDE = '{side}'")
    return page.evaluate(JS, [SELS, PROPS])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--tab", required=True)
    ap.add_argument("--app-url", default="")
    args = ap.parse_args()
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 1000}, http_credentials=credentials())
        app = ctx.new_page()
        app.goto(args.app_url or f"http://127.0.0.1:8000/studio/panel/videos/{args.video}/{args.tab}", wait_until="networkidle")
        ref = ctx.new_page()
        ref.goto(REFERENCE.as_uri() + "#/videos", wait_until="networkidle")
        ref.locator("tr.click").nth(0).click()
        ref.evaluate(f"document.querySelector('[data-a=tab][data-v={args.tab}]').click()")
        ref.wait_for_timeout(400)
        r, a = collect(ref, "ref"), collect(app, "app")
        for key, _, _ in SELS:
            rr, aa = r[key], a[key]
            if not rr and not aa:
                continue
            if not rr or not aa:
                print(f"## {key}: ref={len(rr)} app={len(aa)}")
                continue
            diffs = {pn: (rr[0][pn], aa[0][pn]) for pn in PROPS if rr[0][pn] != aa[0][pn]}
            if diffs:
                print(f"## {key} (ref '{rr[0]['text']}' / app '{aa[0]['text']}')")
                for pn, (x, y) in diffs.items():
                    print(f"   {pn}: ref={x} | app={y}")
        b.close()


main()
