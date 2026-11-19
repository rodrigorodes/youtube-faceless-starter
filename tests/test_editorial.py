import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.editorial import (  # noqa: E402
    CostGuard, GenerateScript, IngestSource, RunFactCheck, ScriptRejected, SourceRefused, StateConflict, VideoNotFound, host_allowed,
)
from app.studio.application.ports import FetchedPage, TextResult  # noqa: E402
from app.studio.domain.claims import extract_claims  # noqa: E402
from app.studio.domain.contracts import FactCheckReport, Scene, Script, SourceSnapshot, UsageEntry, Video, VideoFormat, VideoStatus  # noqa: E402
from app.studio.domain.policy import CostRefused  # noqa: E402

V, P = "v" * 32, "p" * 32
SOURCE = ("Amsterdam Dance Event celebrates 30 years with more than 3,600 artists, 1,300 events and 300 venues across the city.\n"
          "Jean-Michel Jarre opens the festival with a concert at AFAS Live on 21 October to mark 50 years of Oxygène.\n")
ALLOW = ("amsterdam-dance-event.nl", "loveland.nl")


class Videos:
    def __init__(self, status=VideoStatus.IDEA):
        self.status = status
        self.exists = True

    def get_video(self, video_id):
        return Video(id=V, project_id=P, topic="ADE 2026", format=VideoFormat.short, status=self.status) if self.exists else None


class Snapshots:
    def __init__(self):
        self.items = []

    def add(self, video_id, url, text):
        snap = SourceSnapshot(id=f"{len(self.items):032x}", video_id=video_id, url=url, content_sha256="a" * 64, text=text)
        self.items.append(snap)
        return snap

    def list(self, video_id):
        return list(self.items)


class Scripts:
    def __init__(self, videos):
        self.videos, self.saved, self._scenes = videos, [], []

    def save_and_advance(self, video_id, text, drafts, claim_ids, expected, new):
        if self.videos.status != expected:
            return None
        self.videos.status = new
        self.saved.append(text)
        self._scenes = [Scene(id=f"{i:032x}", video_id=video_id, idx=i, narration=d.narration, caption=d.caption, label=d.label,
                              image_prompt=d.image_prompt, claim_ids=d.claim_ids) for i, d in enumerate(drafts)]
        return Script(id="s" * 32, video_id=video_id, version=len(self.saved), text=text, claim_ids=claim_ids)

    def scenes(self, video_id):
        return list(self._scenes)


class Checks:
    def __init__(self, videos):
        self.videos, self.reports = videos, []

    def save(self, video_id, report, advance):
        if advance:
            if self.videos.status != VideoStatus.SCRIPTED:
                return False
            self.videos.status = VideoStatus.FACT_CHECKED
        self.reports.append(report)
        return True


class Usage:
    def __init__(self, video=0.0, month=0.0):
        self.entries, self.video, self.month = [], video, month

    def record(self, video_id, entry):
        self.entries.append(entry)

    def spent_video(self, video_id):
        return self.video

    def spent_month(self):
        return self.month


class Text:
    name = "fake"

    def __init__(self, payload, cost=0.0):
        self.payload, self.cost, self.calls, self.prompts = payload, cost, 0, []

    def cost_estimate(self, prompt):
        return self.cost

    def complete(self, prompt, *, json_schema=None):
        self.calls += 1
        self.prompts.append(prompt)
        raw = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return TextResult(text=raw, usage=UsageEntry(step="script", provider="fake", model="m", cost_usd=0))


class Fetcher:
    def __init__(self):
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        return FetchedPage(text=SOURCE, final_url=url)


@pytest.fixture()
def world():
    videos = Videos()
    return {"videos": videos, "snaps": Snapshots(), "scripts": Scripts(videos), "checks": Checks(videos), "usage": Usage()}


def claim_ids():
    return [c.id for c in extract_claims("s" * 32, SOURCE)]


def good_payload(narrations=None, ids=None):
    ids = ids if ids is not None else claim_ids()
    narrations = narrations or ["Eram mais de três mil e seiscentos artistas.", "Jean-Michel Jarre abriu o festival no AFAS Live."]
    # cada cena cita a claim do seu índice (módulo o nº de narrações); o bloco se repete para dar 4 cenas
    return {"scenes": [{"narration": n, "caption": "Legenda", "label": "QUA", "image_prompt": "wide stage with colorful lights and haze",
                        "claim_ids": [ids[i % len(ids)]]} for i, n in enumerate(narrations)] * 2}


def generator(world, payload, cost=0.0, cap_video=0.0, cap_month=15.0):
    return GenerateScript(world["videos"], world["snaps"], world["scripts"], Text(payload, cost), CostGuard(world["usage"], cap_video, cap_month), world["usage"])


def seed(world):
    IngestSource(Fetcher(), world["snaps"], world["videos"], ALLOW).execute_text(V, "https://amsterdam-dance-event.nl/x", SOURCE)


# ---------- fontes ----------
@pytest.mark.parametrize("url,ok", [
    ("https://amsterdam-dance-event.nl/en/x", True), ("https://www.amsterdam-dance-event.nl/x", True),
    ("https://evil-amsterdam-dance-event.nl/x", False), ("https://amsterdam-dance-event.nl.evil.com/x", False),
    ("https://amsterdam-dance-event.nl@evil.com/x", False), ("file:///etc/passwd", False), ("ftp://amsterdam-dance-event.nl/", False),
    ("https:///x", False), ("not a url", False),
])
def test_allowlist(url, ok):
    assert host_allowed(url, ALLOW) is ok


def test_ingest_url_outside_allowlist_is_refused_without_fetching(world):
    fetcher = Fetcher()
    with pytest.raises(SourceRefused):
        IngestSource(fetcher, world["snaps"], world["videos"], ALLOW).execute_url(V, "https://evil.example/x")
    assert fetcher.urls == []


def test_ingest_url_stores_snapshot_and_unknown_video_is_404(world):
    ing = IngestSource(Fetcher(), world["snaps"], world["videos"], ALLOW)
    assert ing.execute_url(V, "https://amsterdam-dance-event.nl/x").text == SOURCE.strip()
    world["videos"].exists = False
    with pytest.raises(VideoNotFound):
        ing.execute_url(V, "https://amsterdam-dance-event.nl/x")


@pytest.mark.parametrize("url,text", [("ftp://x.example", "texto"), ("https://x.example", "   "), ("https://x.example", "a" * 200_001)])
def test_ingest_text_validation(world, url, text):
    with pytest.raises(SourceRefused):
        IngestSource(Fetcher(), world["snaps"], world["videos"], ALLOW).execute_text(V, url, text)


# ---------- roteiro ----------
def test_generate_persists_valid_script_records_usage_and_advances(world):
    seed(world)
    script = generator(world, good_payload()).execute(V, 4)
    assert script.version == 1 and world["videos"].status == VideoStatus.SCRIPTED
    assert len(world["scripts"].scenes(V)) == 4 and len(world["usage"].entries) == 1 and script.claim_ids


@pytest.mark.parametrize("payload", [
    "isto não é json", {"scenes": []}, {"nada": 1}, {"scenes": [{"narration": "curta"}] * 4},
    {"scenes": [{"narration": "Narração suficiente aqui", "claim_ids": ["inexistente"]}] * 4},
    {"scenes": [{"narration": "Narração suficiente aqui"}] * 2},
    {"scenes": ["texto solto"] * 4},
])
def test_generate_rejects_bad_output_and_persists_nothing(world, payload):
    seed(world)
    with pytest.raises(ScriptRejected):
        generator(world, payload).execute(V, 4)
    assert world["scripts"].saved == [] and world["videos"].status == VideoStatus.IDEA
    assert len(world["usage"].entries) == 1  # a chamada aconteceu e foi contabilizada


def test_generate_rejects_unknown_claim_ids(world):
    seed(world)
    with pytest.raises(ScriptRejected, match="claim"):
        generator(world, good_payload(ids=["naoexiste00"])).execute(V, 4)


def test_generate_requires_sources_and_right_state(world):
    with pytest.raises(SourceRefused, match="sources"):
        generator(world, good_payload()).execute(V, 4)
    seed(world)
    world["videos"].status = VideoStatus.FACT_CHECKED
    with pytest.raises(StateConflict):
        generator(world, good_payload()).execute(V, 4)


def test_regenerate_while_scripted_bumps_version(world):
    seed(world)
    g = generator(world, good_payload())
    assert g.execute(V, 4).version == 1 and g.execute(V, 4).version == 2
    assert world["videos"].status == VideoStatus.SCRIPTED


def test_cost_guard_blocks_paid_model_before_calling_it(world):
    seed(world)
    gen = generator(world, good_payload(), cost=0.5, cap_video=0.0)
    with pytest.raises(CostRefused):
        gen.execute(V, 4)
    assert gen.text_model.calls == 0 and world["usage"].entries == []


def test_cost_guard_monthly_cap(world):
    world["usage"].month = 14.8
    with pytest.raises(CostRefused):
        CostGuard(world["usage"], 5.0, 15.0).check(V, 0.5)
    CostGuard(world["usage"], 5.0, 15.0).check(V, 0.1)


# ---------- checagem factual ----------
def scripted(world, narrations, ids=None):
    seed(world)
    generator(world, good_payload(narrations, ids)).execute(V, 4)


def checker(world, allow=frozenset()):
    return RunFactCheck(world["videos"], world["snaps"], world["scripts"], world["checks"], allow)


def test_fact_check_passes_when_supported_and_advances(world):
    scripted(world, ["Eram mais de três mil e seiscentos artistas.", "Jean-Michel Jarre abriu o festival no AFAS Live."], ids=claim_ids())
    report = checker(world).execute(V)
    assert report.passed and not report.overridden and world["videos"].status == VideoStatus.FACT_CHECKED


def test_fact_check_fails_on_invented_number_and_does_not_advance(world):
    scripted(world, ["Eram mais de quatro mil artistas.", "Jean-Michel Jarre abriu o festival."], ids=claim_ids())
    report = checker(world).execute(V)
    assert not report.passed and world["videos"].status == VideoStatus.SCRIPTED
    assert any(i.value == "4000" for s in report.scenes for i in s.unsupported) and world["checks"].reports == [report]


def test_fact_check_uses_only_cited_claims(world):
    ids = claim_ids()  # ids[0] = frase do 3,600; ids[1] = frase do Jarre/21/50
    scripted(world, ["Jean-Michel Jarre abriu o festival em vinte e um de outubro."], ids=ids)  # cita só a frase dos 3,600
    report = checker(world).execute(V)
    assert not report.passed  # Jarre/21 só existem na outra frase, que a cena não citou


def test_fact_check_also_checks_captions(world):
    seed(world)
    payload = good_payload(["Eram mais de três mil e seiscentos artistas."] * 2, claim_ids())
    for scene in payload["scenes"]:
        scene["caption"] = "No palco: Madonna"
    generator(world, payload).execute(V, 4)
    assert not checker(world).execute(V).passed


@pytest.mark.parametrize("reason", ["", "   ", "\n"])
def test_override_requires_reason(world, reason):
    scripted(world, ["Eram mais de quatro mil artistas.", "Jean-Michel Jarre abriu o festival."], ids=claim_ids())
    with pytest.raises(ValueError, match="reason"):
        checker(world).execute(V, override_reason=reason)
    assert world["checks"].reports == [] and world["videos"].status == VideoStatus.SCRIPTED


def test_override_passes_and_transitions_and_is_recorded(world):
    scripted(world, ["Eram mais de quatro mil artistas.", "Jean-Michel Jarre abriu o festival."], ids=claim_ids())
    report = checker(world).execute(V, override_reason="número conferido manualmente na fonte impressa")
    assert report.passed and report.overridden and report.override_reason and world["videos"].status == VideoStatus.FACT_CHECKED
    assert any(i.value == "4000" for s in report.scenes for i in s.unsupported)  # o motivo da reprovação continua visível


def test_fact_check_wrong_state_and_no_script(world):
    with pytest.raises(StateConflict):
        checker(world).execute(V)  # ainda IDEA
    world["videos"].status = VideoStatus.SCRIPTED
    with pytest.raises(SourceRefused):
        checker(world).execute(V)  # SCRIPTED sem fontes/cenas


def test_allow_names_reaches_the_check(world):
    scripted(world, ["Em Amsterdã, o festival celebrou trinta anos."], ids=claim_ids())
    assert not checker(world).execute(V).passed
    world["videos"].status = VideoStatus.SCRIPTED
    assert checker(world, frozenset({"amsterda"})).execute(V).passed


def test_generate_accepts_json_inside_code_fence(world):
    seed(world)
    fenced = "Claro! Aqui está:\n```json\n" + json.dumps(good_payload()) + "\n```\n"
    assert generator(world, fenced).execute(V, 4).version == 1


def test_prompt_fits_the_bridge_limit_and_only_offered_claims_are_valid(world):
    long_source = "\n".join(f"Event {i} happens in Amsterdam during the festival week with {100 + i} guests and many more details here." for i in range(60))
    IngestSource(Fetcher(), world["snaps"], world["videos"], ALLOW).execute_text(V, "https://amsterdam-dance-event.nl/x", long_source)
    gen = generator(world, good_payload(ids=["x"]))
    with pytest.raises(ScriptRejected):
        gen.execute(V, 4)
    assert len(gen.text_model.prompts[0]) <= 4000
