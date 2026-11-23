"""Read-only local Chromium captures. Never persists credentials or response bodies."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs/backlogs/faceless-visual-evolution 2/prototype-v4-v3/index.html"


def credentials():
    # Read only the two local browser credentials, never log environment contents.
    values = {}
    for line in (ROOT / ".env").read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key in {"STUDIO_BROWSER_USER", "STUDIO_BROWSER_PASSWORD"}:
            values[key] = value.strip().strip("'\"")
    return {"username": values["STUDIO_BROWSER_USER"], "password": values["STUDIO_BROWSER_PASSWORD"]}


def measure(page):
    result = page.evaluate("""() => Object.fromEntries(
      ['body','.side','.logo','.top','.content','h1','.hero','.card','.modecard','.eyebrow']
      .map(selector => {
        const el=document.querySelector(selector); if(!el)return [selector,null];
        const s=getComputedStyle(el),r=el.getBoundingClientRect();
        return [selector,{x:r.x,y:r.y,width:r.width,height:r.height,
          font:s.fontFamily,fontSize:s.fontSize,fontWeight:s.fontWeight,
          lineHeight:s.lineHeight,padding:s.padding,margin:s.margin,
          background:s.backgroundColor,border:s.borderRadius}];
      }))""")
    session = page.context.new_cdp_session(page)
    session.send("DOM.enable")
    session.send("CSS.enable")
    doc = session.send("DOM.getDocument")
    node = session.send("DOM.querySelector", {"nodeId": doc["root"]["nodeId"], "selector": "h1"})
    result["renderedFonts"] = session.send("CSS.getPlatformFontsForNode", {"nodeId": node["nodeId"]})["fonts"] if node["nodeId"] else []
    result["overflow"] = page.evaluate("document.documentElement.scrollWidth > innerWidth")
    session.detach()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--base", default="http://localhost:8000")
    args = parser.parse_args()
    if args.base not in {"http://localhost:8000", "http://127.0.0.1:8000"}:
        raise ValueError("Only the local app is supported")
    out = ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in (1440, 390):
            context = browser.new_context(viewport={"width": width, "height": 1000}, http_credentials=credentials())
            page = context.new_page()
            for name, ref, app in (
                ("home", "#/home", "/studio/panel"),
                ("new", "#/new", "/studio/panel/novo-video"),
                ("videos", "#/videos", "/studio/panel/videos"),
                ("settings", "#/settings", "/studio/configuracoes/canais"),
                ("channel", "#/channel/new", "/studio/canais/novo"),
            ):
                for kind, url in (("reference", REFERENCE.as_uri() + ref), ("app", args.base + app)):
                    page.goto(url, wait_until="networkidle")
                    page.locator("h1").wait_for()
                    page.screenshot(path=str(out / f"{kind}-{name}-{width}.png"), full_page=True)
                    report[f"{kind}-{name}-{width}"] = measure(page)
            context.close()
        browser.close()
    (out / "metrics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Saved screenshots and computed styles to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
