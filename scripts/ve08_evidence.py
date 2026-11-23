"""VE-08: evidência de fidelidade do workspace de vídeo (Cenas e Composição) — protótipo x HTML real do app.

O app real não tem nenhum vídeo com roteiro, então o HTML real do workspace é servido sobre o backend
simulado de `tests/ve08/harness.py`, com as mesmas cenas do vídeo `v2` do protótipo. Nada é gerado nem pago.
Saída: docs/visual-evidence/ve-08/{scenes,composition}-{reference,app,diff}-{1440,768,390}.png + relatório.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "renderer"), str(ROOT / "scripts")]
import fidelity_gate as fg  # noqa: E402
from tests.ve08.harness import FakeStudio, install, workspace_html  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402

SEED = [
    ("Gancho", "Sob os campos da Capadócia existe uma cidade inteira escondida a mais de 60 metros de profundidade.",
     "vista aérea da Capadócia, pôr do sol"),
    ("Contexto", "Derinkuyu tinha ventilação, cozinhas, igrejas e até estábulos, capaz de abrigar cerca de 20 mil pessoas.",
     "corredor de pedra esculpida, tochas"),
    ("Revelação", "Portas de pedra circulares podiam ser fechadas por dentro, transformando a cidade em uma fortaleza.",
     "porta de pedra circular rolando, câmera baixa"),
]
TITLE = "A cidade subterrânea de Derinkuyu"
AREAS = {"scenes": ("cenas", "go('#/video/v2/cenas')"), "composition": ("composicao", "go('#/video/v2/composicao')")}


def main():
    out = ROOT / "docs/visual-evidence/ve-08"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for key, (area, ref_js) in AREAS.items():
            for vp, (w, h) in fg.VIEWPORTS.items():
                st = FakeStudio(seed=SEED, with_media=(0,))
                st.scenes[0]["duration_s"] = None
                st.assets["asset-0"] = ("pexels", "image")
                ctx = browser.new_context(viewport={"width": w, "height": h}, service_workers="block")
                ref, app = ctx.new_page(), ctx.new_page()
                ref.goto(fg.REFERENCE.as_uri(), wait_until="networkidle")
                ref.evaluate(ref_js)
                ref.wait_for_timeout(350)
                app.goto(install(app, st, lambda: workspace_html(st, area=area, fmt=VideoFormat.long, topic=TITLE),
                                 area=area))
                app.wait_for_timeout(400)
                rp, ap_ = out / f"{key}-reference-{vp}.png", out / f"{key}-app-{vp}.png"
                for page in (ref, app):
                    full = page.evaluate(fg.SCROLL_H_JS)
                    page.set_viewport_size({"width": w, "height": max(h, min(int(full), 9000))})
                    page.wait_for_timeout(150)
                ref.screenshot(path=str(rp), full_page=True)
                app.screenshot(path=str(ap_), full_page=True)
                trows, tratio = fg.seq_diff(ref.evaluate(fg.TEXT_JS), app.evaluate(fg.TEXT_JS))
                frows, fratio = fg.seq_diff(ref.evaluate(fg.FIELDS_JS), app.evaluate(fg.FIELDS_JS))
                srows = fg.style_diff(ref.evaluate(fg.STYLE_JS, fg.STYLE_PROPS), app.evaluate(fg.STYLE_JS, fg.STYLE_PROPS))
                pix, hr, ha = fg.pixel_diff(rp, ap_)
                _diff_image(rp, ap_, out / f"{key}-diff-{vp}.png")
                ro, ao = ref.evaluate(fg.OVERFLOW_JS), app.evaluate(fg.OVERFLOW_JS)
                rep = {"screen": key, "viewport": vp, "text_similarity": tratio, "text_diffs": len(trows),
                       "field_similarity": fratio, "field_diffs": len(frows), "style_diffs": len(srows),
                       "pixel_diff_pct": pix, "height_ref": hr, "height_app": ha,
                       "overflow_ref": ro["sw"] - ro["cw"], "overflow_app": ao["sw"] - ao["cw"]}
                rows.append(rep)
                lines = [json.dumps(rep, ensure_ascii=False), "", "## TEXTO (ref -> app)"]
                lines += [f"[{t}] REF={a[:6]} | APP={b[:6]}" for t, a, b in trows[:60]]
                lines += ["", "## CAMPOS/BOTOES (ref -> app)"]
                lines += [f"[{t}] REF={a[:6]} | APP={b[:6]}" for t, a, b in frows[:60]]
                lines += ["", "## ESTILOS COMPUTADOS (mesmo texto)"]
                for text, rt, at, d in srows[:60]:
                    lines.append(f"'{text}' ref<{rt}> app<{at}>")
                    lines += [f"    {k}: ref={v[0]} | app={v[1]}" for k, v in d.items()]
                (out / f"{key}-report-{vp}.txt").write_text("\n".join(lines), encoding="utf-8")
                ctx.close()
        browser.close()
    _progress_states(browser_factory=sync_playwright, out=out)
    (out / "summary-scenes-composition.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        print(f"{r['screen']:<12}{r['viewport']:>4} text={r['text_similarity']:>5}% ({r['text_diffs']}) fields={r['field_similarity']:>5}% "
              f"({r['field_diffs']}) style={r['style_diffs']} pix={r['pixel_diff_pct']}% h={r['height_ref']}/{r['height_app']} "
              f"ovf={r['overflow_ref']}/{r['overflow_app']}")


def _progress_states(browser_factory, out):
    """Estados do dock/progresso no storyboard (VE-08.5–7): antes, em execução, falha e concluído (app real, backend simulado)."""
    from app.studio.application.ports import LatestRun
    from app.studio.domain.contracts import VideoStatus
    stages = ["research", "script", "factcheck", "storyboard", "assets", "render", "qa", "approval", "publish"]
    run = LatestRun(run_id="r" * 32, state="RUNNING")
    states = {
        "before": dict(status=VideoStatus.SCRIPTED),
        "running": dict(status=VideoStatus.STORYBOARDED, latest_run=run, run_stages=list(zip(
            stages, ["SUCCEEDED"] * 4 + ["RUNNING"] + ["PENDING"] * 4))),
        "stage-done": dict(status=VideoStatus.STORYBOARDED, latest_run=run, run_stages=list(zip(
            stages, ["SUCCEEDED"] * 5 + ["RUNNING"] + ["PENDING"] * 3))),
        "failed": dict(status=VideoStatus.FAILED),
        "done": dict(status=VideoStatus.AWAITING_APPROVAL),
    }
    with browser_factory() as p:
        browser = p.chromium.launch()
        for name, kw in states.items():
            for vp, (w, h) in fg.VIEWPORTS.items():
                st = FakeStudio(seed=SEED, with_media=(0,))
                done = sum(1 for _s, state in kw.get("run_stages", ()) if state == "SUCCEEDED")
                if "latest_run" in kw:
                    st.runs["r" * 32] = {"polls": done - 1}   # o 1º polling devolve o mesmo retrato da página
                ctx = browser.new_context(viewport={"width": w, "height": h}, service_workers="block")
                pg = ctx.new_page()
                pg.goto(install(pg, st, lambda: workspace_html(st, area="cenas", fmt=VideoFormat.long, topic=TITLE, **kw)))
                pg.wait_for_timeout(300)
                pg.screenshot(path=str(out / f"progress-state-{name}-{vp}.png"), full_page=True)
                ctx.close()
        browser.close()


def _diff_image(a_path, b_path, out_path):
    from PIL import Image, ImageChops
    a, b = Image.open(a_path).convert("RGB"), Image.open(b_path).convert("RGB")
    h = min(a.height, b.height)
    a, b = a.crop((0, 0, a.width, h)), b.crop((0, 0, b.width, h)).resize((a.width, h))
    mask = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 24 else 0)
    base = Image.blend(a, Image.new("RGB", a.size, (0, 0, 0)), 0.65)
    base.paste(Image.new("RGB", a.size, (255, 0, 80)), mask=mask)
    base.save(out_path)


if __name__ == "__main__":
    main()
