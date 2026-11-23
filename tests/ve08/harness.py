"""VE-08: harness Playwright — o HTML real do workspace servido sobre um backend simulado e determinístico.

Nada aqui toca o Studio real nem gera mídia paga: `FakeStudio` reproduz os contratos de cena
(`/script/scenes`, `/scenes/{id}/media|broll`, `/production-runs`) com a mesma semântica do backend
(editar texto limpa a mídia da cena; B-roll não cria versão; reordenar preserva ids).
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "renderer"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.studio.api.panel_video_workspace import render_video_workspace  # noqa: E402
from app.studio.domain.contracts import Asset, AssetKind, Scene, Script, Video, VideoFormat, VideoStatus  # noqa: E402

BASE = "http://app.test"
VID = "a" * 32
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")

SEED = [
    ("Gancho", "Você sabia que a luz do sol demora oito minutos para chegar até aqui?", "Sol brilhando sobre a Terra vista do espaço"),
    ("Mecanismo", "Os fótons atingem o silício e liberam elétrons livres na célula.", "Diagrama macro de elétrons em uma célula solar"),
    ("Conversão", "O inversor transforma a corrente contínua em corrente alternada.", "Inversor moderno na parede com leds verdes acesos"),
]


class FakeStudio:
    def __init__(self, *, seed=SEED, with_media=(0,), fail_on: str | None = None):
        self.version = 1
        self.n = 0
        self.fail_on = fail_on
        self.calls: list[tuple[str, str, dict]] = []
        self.runs: dict[str, dict] = {}
        self.assets = {"asset-0": ("ai-generated:fake", "image")}
        self.scenes = []
        for i, (label, text, prompt) in enumerate(seed):
            self.scenes.append(self._scene(label, text, prompt, f"asset-{i}" if i in with_media else None,
                                           6.0 if i in with_media else None))
            if i in with_media:
                self.assets[f"asset-{i}"] = ("ai-generated:fake", "image")

    def _scene(self, label, text, prompt, asset=None, dur=None):
        self.n += 1
        return {"id": f"{self.n:032x}", "video_id": VID, "idx": 0, "narration": text, "caption": "", "label": label,
                "image_prompt": prompt, "claim_ids": [], "asset_id": asset, "duration_s": dur,
                "broll_enabled": False, "broll_note": None}

    def model_scenes(self):
        out = []
        for i, s in enumerate(self.scenes):
            out.append(Scene(**{**s, "idx": i}))
        return out

    def script(self):
        return Script(id="s" * 32, video_id=VID, version=self.version, text="x", claim_ids=[])

    def out(self):
        self.version += 1
        return {"script": self.script().model_dump(mode="json"),
                "scenes": [{**s, "idx": i} for i, s in enumerate(self.scenes)]}

    def asset_map(self):
        return {i: Asset(id=s["asset_id"], kind=AssetKind(self.assets[s["asset_id"]][1]), cache_key="k" * 64, path="x.png",
                         provider="fake", model="m", license=self.assets[s["asset_id"]][0])
                for i, s in enumerate(self.scenes) if s["asset_id"]}

    # -- rotas ----------------------------------------------------------------
    def handle(self, route, request):
        url = request.url.replace(BASE, "")
        method = request.method
        body = {}
        if request.post_data:
            try:
                body = json.loads(request.post_data)
            except ValueError:
                body = {}
        m = re.match(r"/studio/videos/\w+/(.*)$", url.split("?")[0])
        if not m:
            return route.continue_()
        path = m.group(1)
        self.calls.append((method, path, body))
        if self.fail_on and self.fail_on in path:
            return route.fulfill(status=409, content_type="application/json",
                                 body=json.dumps({"detail": "script changed (simulado)"}))
        j = lambda d, status=200: route.fulfill(status=status, content_type="application/json", body=json.dumps(d))
        if re.fullmatch(r"scenes/\w+/asset", path):
            return route.fulfill(status=200, content_type="image/png", body=PNG)
        if path == "script/scenes/reorder" and method == "POST":
            self.scenes = [self.scenes[i] for i in body["order"]]
            return j(self.out())
        mm = re.fullmatch(r"script/scenes/(\d+)", path)
        if mm and method == "POST":
            s = self.scenes[int(mm.group(1))]
            if s["narration"] != body["narration"].strip() or s["image_prompt"] != (body.get("image_prompt") or s["image_prompt"]):
                s["asset_id"] = None
                s["duration_s"] = None
            s["narration"] = body["narration"].strip()
            s["image_prompt"] = body.get("image_prompt") or s["image_prompt"]
            return j(self.out())
        if mm and method == "DELETE":
            del self.scenes[int(mm.group(1))]
            return j(self.out())
        if path == "script/scenes" and method == "POST":
            sc = self._scene(body.get("label", ""), body["narration"], body["image_prompt"])
            self.scenes.insert(body.get("position", len(self.scenes)), sc)
            return j(self.out())
        mm = re.fullmatch(r"scenes/(\w+)/broll", path)
        if mm:
            s = next(x for x in self.scenes if x["id"] == mm.group(1))
            s["broll_enabled"], s["broll_note"] = body["enabled"], body.get("note")
            return j({"scene_id": s["id"], "enabled": body["enabled"], "note": body.get("note"), "changed": True})
        mm = re.fullmatch(r"scenes/(\w+)/media", path)
        if mm:
            s = next(x for x in self.scenes if x["id"] == mm.group(1))
            s["asset_id"] = body["asset_id"]
            return j({"scene_id": s["id"], "asset": {"id": s["asset_id"], "kind": "image", "license": "ai-generated:fake"},
                      "changed": True, "reason": ""})
        if path == "style-patch" and method == "PATCH":
            self.patches = getattr(self, "patches", []) + [body]
            return j({"revision": body.get("expected_revision", 0) + 1})
        if path == "production-runs" and method == "POST":
            if self.runs:
                rid = next(iter(self.runs))
                return j({"run_id": rid, "state": "RUNNING", "mode": "diretor", "created": False}, 202)
            rid = "r" * 32
            self.runs[rid] = {"polls": 0}
            return j({"run_id": rid, "state": "CREATED", "mode": "diretor", "created": True}, 202)
        mm = re.fullmatch(r"production-runs/(\w+)", path)
        if mm and method == "GET":
            run = self.runs[mm.group(1)]
            run["polls"] += 1
            stages = ["research", "script", "factcheck", "storyboard", "assets", "render", "qa", "approval", "publish"]
            done = min(run["polls"], len(stages))
            states = ["SUCCEEDED"] * done + ["RUNNING"] * (1 if done < len(stages) else 0)
            states += ["PENDING"] * (len(stages) - len(states))
            return j({"run_id": mm.group(1), "video_id": VID, "state": "RUNNING", "mode": "diretor", "stages": [
                {"stage": s, "state": st, "attempt": 1, "fencing_token": 1} for s, st in zip(stages, states)],
                "available_stages": [], "unavailable_stages": [], "events": []})
        return j({"detail": "not found"}, 404)


def workspace_html(studio: FakeStudio, area="cenas", status=VideoStatus.SCRIPTED, *, run_stages=None, latest_run=None,
                   fmt=VideoFormat.short, topic="Como funciona a energia solar"):
    from app.studio.application.panel import VideoDetailView
    from app.studio.domain.panel import classify
    video = Video(id=VID, project_id="p" * 32, topic=topic, format=fmt, status=status)
    view = VideoDetailView(video=video, stage=classify(status), cost_text="sem registro de uso", steps=[], usage=[],
                           render_error=None, publication=None, sources=[], latest_run=latest_run)
    html, _headers = render_video_workspace(view, area, scenes=studio.model_scenes(), script=studio.script(),
                                            scene_assets=studio.asset_map(), run_stages=run_stages,
                                            channel_voice="Voz Aria", channel_name="Canal Teste", sources=[])
    return html


def install(page, studio: FakeStudio, html: str, area="cenas"):
    """Serve o workspace e o backend simulado; o resto da rede é bloqueado (nada sai da máquina)."""
    def route(r, request):
        url = request.url
        if url.split("?")[0] == f"{BASE}/studio/panel/videos/{VID}/{area}":
            return r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html() if callable(html) else html)
        if url.startswith(f"{BASE}/studio/videos/"):
            return studio.handle(r, request)
        return r.fulfill(status=404, body="")
    page.route("**/*", route)
    return f"{BASE}/studio/panel/videos/{VID}/{area}"
