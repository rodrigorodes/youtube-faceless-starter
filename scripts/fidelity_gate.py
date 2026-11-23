"""Fidelity Gate: protótipo v4-v3 x app local, por tela e viewport (somente leitura).

Para cada tela e viewport (1440x1000, 768x1000, 390x844) gera:
  - screenshots full-page de protótipo e app;
  - diff de texto visível (ordem do DOM), inventário de campos/botões, overflow horizontal;
  - diff de estilos computados em elementos com o mesmo texto estático nos dois lados;
  - diff de pixels (fração de pixels diferentes na área comum + diferença de altura).
Nada é persistido além dos artefatos em --output; credenciais vêm do .env e nunca são impressas.
"""
import argparse
import difflib
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from compare_visual_reference import REFERENCE, ROOT, credentials  # noqa: E402

VIEWPORTS = {"1440": (1440, 1000), "768": (768, 1000), "390": (390, 844)}
APP = "http://127.0.0.1:8000"
VID = "661b9715244941ee9f9dcceecc44a5e4"

# nome -> (js executado no protótipo, rota do app)
SCREENS = {
    "home": ("go('#/home')", "/studio/panel"),
    "new": ("go('#/new')", "/studio/panel/novo-video"),
    "videos": ("go('#/videos')", "/studio/panel/videos"),
    "ideas": ("go('#/ideas')", "/studio/panel/tendencias"),
    "analytics": ("go('#/analytics')", "/studio/panel/analytics"),
    "library": ("go('#/library')", "/studio/panel/estilos"),
    "settings-canais": ("S.setTab='canais';go('#/settings')", "/studio/configuracoes/canais"),
    "settings-marca": ("S.setTab='marca';go('#/settings')", "/studio/configuracoes/marca"),
    "settings-producao": ("S.setTab='producao';go('#/settings')", "/studio/configuracoes/producao"),
    "settings-conexoes": ("S.setTab='conexoes';go('#/settings')", "/studio/panel/conexoes"),
    "wizard": ("go('#/channel/new')", "/studio/canais/novo"),
    "video-cenas": ("go('#/video/v2/cenas')", f"/studio/panel/videos/{VID}/cenas"),
    "video-fontes": ("go('#/video/v2/fontes')", f"/studio/panel/videos/{VID}/fontes"),
    "video-composicao": ("go('#/video/v2/composicao')", f"/studio/panel/videos/{VID}/composicao"),
    "video-qualidade": ("go('#/video/v1/qualidade')", f"/studio/panel/videos/{VID}/qualidade"),
    "video-publicacao": ("go('#/video/v1/publicacao')", f"/studio/panel/videos/{VID}/publicacao"),
    "video-producao": ("go('#/video/v2/producao')", f"/studio/panel/videos/{VID}/producao"),
}

TEXT_JS = """() => {
  const out = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const t = n.textContent.replace(/\\s+/g, ' ').trim();
    if (!t) continue;
    const el = n.parentElement;
    if (!el || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'OPTION'].includes(el.tagName) || el.closest('.indicador-carregando,.skip,[aria-hidden=true]')) continue;
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    if (s.display === 'none' || s.visibility === 'hidden' || (!r.width && !r.height) || (r.width <= 2 && r.height <= 2) || r.right <= 0 || r.x < -500) continue;
    out.push(t);
  }
  return out;
}"""

FIELDS_JS = """() => [...document.querySelectorAll('input,select,textarea,button,a.btn,summary')].filter(el => {
  const r = el.getBoundingClientRect(), s = getComputedStyle(el);
  return r.width && r.height && s.visibility !== 'hidden' && !el.classList.contains('sr-only');
}).map(el => el.tagName.toLowerCase() + (el.type ? '[' + el.type + ']' : '') + ':' +
  ((el.innerText || el.placeholder || el.getAttribute('aria-label') || el.name || '').replace(/\\s+/g, ' ').trim().slice(0, 40)))"""

STYLE_PROPS = ["fontFamily", "fontSize", "fontWeight", "lineHeight", "letterSpacing", "color", "backgroundColor",
               "borderTopWidth", "borderTopColor", "borderTopLeftRadius", "paddingTop", "paddingRight",
               "paddingBottom", "paddingLeft", "marginTop", "marginBottom", "display", "gap", "textTransform",
               "boxShadow", "textAlign"]
STYLE_JS = """(props) => {
  const out = {};
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const t = n.textContent.replace(/\\s+/g, ' ').trim();
    if (!t || t.length > 60) continue;
    const el = n.parentElement;
    if (!el || ['SCRIPT', 'STYLE', 'OPTION'].includes(el.tagName)) continue;
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (!r.width || !r.height || s.display === 'none') continue;
    if (out[t]) continue;
    const o = {tag: el.tagName.toLowerCase(), cls: typeof el.className === 'string' ? el.className : ''};
    props.forEach(p => o[p] = s[p]);
    out[t] = o;
  }
  return out;
}"""
OVERFLOW_JS = "() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})"


def pixel_diff(a_path, b_path):
    from PIL import Image, ImageChops
    a, b = Image.open(a_path).convert("RGB"), Image.open(b_path).convert("RGB")
    h = min(a.height, b.height)
    ca, cb = a.crop((0, 0, a.width, h)), b.crop((0, 0, b.width, h))
    if ca.size != cb.size:
        cb = cb.resize(ca.size)
    diff = ImageChops.difference(ca, cb).convert("L").point(lambda v: 255 if v > 24 else 0)
    changed = sum(1 for v in diff.tobytes() if v) / max(1, diff.width * diff.height)
    return round(changed * 100, 2), a.height, b.height


def side_by_side(a_path, b_path, out_path):
    from PIL import Image
    a, b = Image.open(a_path).convert("RGB"), Image.open(b_path).convert("RGB")
    canvas = Image.new("RGB", (a.width + b.width + 8, max(a.height, b.height)), (255, 0, 255))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + 8, 0))
    canvas.save(out_path)


def seq_diff(ref, app):
    sm = difflib.SequenceMatcher(None, ref, app, autojunk=False)
    rows = [(tag, ref[i1:i2], app[j1:j2]) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]
    return rows, round(sm.ratio() * 100, 1)


def style_diff(ref, app):
    rows = []
    for text, r in ref.items():
        a = app.get(text)
        if not a:
            continue
        d = {p: (r[p], a[p]) for p in STYLE_PROPS if r[p] != a[p]}
        if d:
            rows.append((text, r["tag"] + "." + str(r["cls"]), a["tag"] + "." + str(a["cls"]), d))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="docs/visual-evidence/fidelity")
    ap.add_argument("--only", default="")
    ap.add_argument("--viewports", default="1440,768,390")
    ap.add_argument("--app-url", default="", help="override da URL do app (só com --only de uma tela)")
    ap.add_argument("--max-rows", type=int, default=60)
    args = ap.parse_args()
    out = ROOT / args.output
    summary = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, (ref_js, app_route) in SCREENS.items():
            if args.only and name not in args.only.split(","):
                continue
            for vp in args.viewports.split(","):
                w, h = VIEWPORTS[vp]
                ctx = browser.new_context(viewport={"width": w, "height": h}, http_credentials=credentials())
                folder = out / name
                folder.mkdir(parents=True, exist_ok=True)
                ref = ctx.new_page()
                ref.goto(REFERENCE.as_uri(), wait_until="networkidle")
                ref.evaluate(ref_js)
                ref.wait_for_timeout(350)
                app = ctx.new_page()
                url = args.app_url if args.app_url else APP + app_route
                app.goto(url, wait_until="networkidle")
                app.wait_for_timeout(250)
                rp, ap_ = folder / f"{vp}-reference.png", folder / f"{vp}-app.png"
                ref.screenshot(path=str(rp), full_page=True)
                app.screenshot(path=str(ap_), full_page=True)
                trows, tratio = seq_diff(ref.evaluate(TEXT_JS), app.evaluate(TEXT_JS))
                frows, fratio = seq_diff(ref.evaluate(FIELDS_JS), app.evaluate(FIELDS_JS))
                srows = style_diff(ref.evaluate(STYLE_JS, STYLE_PROPS), app.evaluate(STYLE_JS, STYLE_PROPS))
                ro, ao = ref.evaluate(OVERFLOW_JS), app.evaluate(OVERFLOW_JS)
                pix, hr, ha = pixel_diff(rp, ap_)
                side_by_side(rp, ap_, folder / f"{vp}-side.png")
                report = {
                    "screen": name, "viewport": vp, "text_similarity": tratio, "text_diffs": len(trows),
                    "field_similarity": fratio, "field_diffs": len(frows), "style_diffs": len(srows),
                    "pixel_diff_pct": pix, "height_ref": hr, "height_app": ha,
                    "overflow_ref": ro["sw"] - ro["cw"], "overflow_app": ao["sw"] - ao["cw"],
                }
                summary.append(report)
                lines = [json.dumps(report, ensure_ascii=False), "", "## TEXTO (ref -> app)"]
                for tag, a, b in trows[:args.max_rows]:
                    lines.append(f"[{tag}] REF={a[:6]} | APP={b[:6]}")
                lines += ["", "## CAMPOS/BOTOES (ref -> app)"]
                for tag, a, b in frows[:args.max_rows]:
                    lines.append(f"[{tag}] REF={a[:6]} | APP={b[:6]}")
                lines += ["", "## ESTILOS COMPUTADOS (mesmo texto)"]
                for text, rt, at, d in srows[:args.max_rows]:
                    lines.append(f"'{text}' ref<{rt}> app<{at}>")
                    lines += [f"    {k}: ref={v[0]} | app={v[1]}" for k, v in d.items()]
                (folder / f"{vp}-report.txt").write_text("\n".join(lines), encoding="utf-8")
                ctx.close()
        browser.close()
    prev = {}
    if args.only and (out / "summary.json").exists():
        prev = {(r["screen"], r["viewport"]): r for r in json.loads((out / "summary.json").read_text())}
    prev.update({(r["screen"], r["viewport"]): r for r in summary})
    (out / "summary.json").write_text(json.dumps(list(prev.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    for r in summary:
        print(f"{r['screen']:<18}{r['viewport']:>4} text={r['text_similarity']:>5}% ({r['text_diffs']:>3}) "
              f"fields={r['field_similarity']:>5}% ({r['field_diffs']:>3}) style={r['style_diffs']:>3} "
              f"pix={r['pixel_diff_pct']:>5}% h={r['height_ref']}/{r['height_app']} "
              f"ovf={r['overflow_ref']}/{r['overflow_app']}")


if __name__ == "__main__":
    main()
