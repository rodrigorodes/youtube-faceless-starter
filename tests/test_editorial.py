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

# IDs hexadecimais: a configuração efetiva valida id/projeto, então os stubs seguem o contrato.
V, P = "b" * 32, "a" * 32
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

    def latest(self, video_id):
        return Script(id="s" * 32, video_id=video_id, version=len(self.saved), text="", claim_ids=[]) if self.saved else None


class Checks:
    def __init__(self, videos):
        self.videos, self.reports, self.versions, self.scripts = videos, [], [], None

    def save(self, video_id, report, advance, script_version):
        self.versions.append(script_version)
        if advance:
            if self.scripts is not None and script_version != len(self.scripts.saved):
                return False  # o roteiro mudou depois da leitura (regeração concorrente)
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
    scripts = Scripts(videos)
    checks = Checks(videos)
    checks.scripts = scripts
    return {"videos": videos, "snaps": Snapshots(), "scripts": scripts, "checks": checks, "usage": Usage()}


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
    ("https://evil.com\\.amsterdam-dance-event.nl/", False), ("https://evil.com%5c.amsterdam-dance-event.nl/", False),
    ("https://ev il.amsterdam-dance-event.nl/", False), ("https://amsterdam-dance-event.nl:22/x", False),
    ("https://amsterdam-dance-event.nl:abc/x", False), ("https://amsterdam-dance-event.nl:99999/x", False),
    ("https://amsterdam-dance-event.nl:443/x", True), ("http://amsterdam-dance-event.nl:80/x", True),
    ("https://exämple.amsterdam-dance-event.nl/", False), ("https://amsterdam-dance-event.nl./x", False),
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


def test_usable_source_clears_the_source_refused_at_the_script_stage(world):
    """A saída do beco sem saída do run preso: com fonte aproveitável, o stage de roteiro segue."""
    with pytest.raises(SourceRefused, match="add sources first"):
        generator(world, good_payload()).execute(V, 4)
    seed(world)
    assert generator(world, good_payload()).execute(V, 4).version == 1
    assert world["videos"].status == VideoStatus.SCRIPTED


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
    flagged = {i.value for s in report.scenes for i in s.unsupported}
    assert not report.passed and {"jarre", "21"} <= flagged  # existem só na outra frase, que a cena não citou


def test_fact_check_also_checks_captions(world):
    seed(world)
    payload = good_payload(["Eram mais de três mil e seiscentos artistas."] * 2, claim_ids()[:1])
    for scene in payload["scenes"]:
        scene["caption"] = "No palco: Madonna"
    generator(world, payload).execute(V, 4)
    report = checker(world).execute(V)
    assert not report.passed and {i.value for s in report.scenes for i in s.unsupported} == {"madonna"}


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


# ---------- achados da revisão ----------
def test_fact_check_is_bound_to_the_script_version_it_read(world):
    scripted(world, ["Eram mais de três mil e seiscentos artistas.", "Jean-Michel Jarre abriu o festival no AFAS Live."], ids=claim_ids())
    original_scenes = world["scripts"].scenes

    def scenes_then_regenerate(video_id):  # regeração concorrente depois da leitura
        found = original_scenes(video_id)
        generator(world, good_payload()).execute(V, 4)
        return found

    world["scripts"].scenes = scenes_then_regenerate
    with pytest.raises(StateConflict):
        checker(world).execute(V)
    assert world["videos"].status == VideoStatus.SCRIPTED and world["checks"].reports == []


def test_fact_check_passes_the_checked_version_to_the_repository(world):
    scripted(world, ["Eram mais de três mil e seiscentos artistas.", "Jean-Michel Jarre abriu o festival no AFAS Live."], ids=claim_ids())
    checker(world).execute(V)
    assert world["checks"].versions == [1]


def test_label_and_image_prompt_are_checked(world):
    seed(world)
    payload = good_payload(["Eram mais de três mil e seiscentos artistas."] * 2, claim_ids())
    payload["scenes"][0]["label"] = "QUA 24/10"
    payload["scenes"][1]["image_prompt"] = "portrait of Madonna on a stage with lights"
    generator(world, payload).execute(V, 4)
    report = checker(world).execute(V)
    flagged = {i.value for s in report.scenes for i in s.unsupported}
    assert {"24", "madonna"} <= flagged


@pytest.mark.parametrize("scene", [
    {"narration": "Narração suficiente aqui", "image_prompt": "wide stage with colorful lights"},
    {"narration": "Narração suficiente aqui", "image_prompt": "wide stage with colorful lights", "claim_ids": []},
    {"narration": "Narração suficiente aqui\u0000", "image_prompt": "wide stage with colorful lights", "claim_ids": ["__ID__"]},
    {"narration": "Narração suficiente aqui", "image_prompt": "wide stage with colorful lights", "claim_ids": ["__ID__"], "label": "a\u0000"},
])
def test_every_scene_must_cite_claims_and_have_no_nul(world, scene):
    seed(world)
    cid = claim_ids()[0]
    scene = json.loads(json.dumps(scene).replace("__ID__", cid))
    with pytest.raises(ScriptRejected):
        generator(world, {"scenes": [scene] * 2}).execute(V, 4)
    assert world["scripts"].saved == []


def test_deeply_nested_model_output_is_rejected_not_a_crash(world):
    seed(world)
    with pytest.raises(ScriptRejected):
        generator(world, "{" + '{"a":' * 100000 + "1" + "}" * 100000).execute(V, 4)


def test_prompt_cut_claims_are_not_valid_ids(world):
    long_source = "\n".join(f"Event {i} happens in Amsterdam during the festival week with {100 + i} guests and many more details here." for i in range(60))
    IngestSource(Fetcher(), world["snaps"], world["videos"], ALLOW).execute_text(V, "https://amsterdam-dance-event.nl/x", long_source)
    from app.studio.application.editorial import _claims
    all_ids = [c.id for c in _claims(world["snaps"].list(V))]
    gen = generator(world, "placeholder")
    gen.text_model.payload = good_payload(ids=[all_ids[-1]])  # existe na fonte, mas foi cortada do prompt
    with pytest.raises(ScriptRejected, match="unknown claim ids"):
        gen.execute(V, 4)


def test_per_video_cap_accumulates_through_generate(world):
    seed(world)
    world["usage"].video = 0.9
    gen = generator(world, good_payload(), cost=0.2, cap_video=1.0)
    with pytest.raises(CostRefused, match="per-video"):
        gen.execute(V, 4)
    assert gen.text_model.calls == 0
    ok = generator(world, good_payload(), cost=0.05, cap_video=1.0)
    assert ok.execute(V, 4).version == 1


# ---------- F04: contexto editorial derivado da configuração efetiva ----------
from app.studio.application.editorial import (  # noqa: E402
    DEFAULT_DURATION_S,
    DEFAULT_LANGUAGE,
    EditorialContext,
    build_prompt,
    language_label,
)
from app.studio.domain.channel import ChannelProfile  # noqa: E402
from app.studio.domain.effective_config import EDITORIAL_FIELDS, resolve_effective_config  # noqa: E402


def video() -> Video:
    return Video(id=V, project_id=P, topic="ADE 2026", format=VideoFormat.short, status=VideoStatus.IDEA)


def channel(**kw) -> ChannelProfile:
    base = {"id": "c" * 32, "project_id": P, "name": "História"}
    base.update(kw)
    return ChannelProfile(**base)


def prompt_claims():
    return extract_claims("s" * 32, SOURCE)


def test_editorial_context_derives_from_the_effective_config_with_provenance():
    config = resolve_effective_config(video=video(), channel=channel(
        language="en-US", audience="produtores de eventos", narrative="documental em três atos",
        pillars=["trilha", "palco"], cta="inscreva-se no canal", target_duration_s=90))
    context = EditorialContext.from_effective_config(config)

    assert (context.language, context.audience, context.narrative, context.cta) == \
        ("en-US", "produtores de eventos", "documental em três atos", "inscreva-se no canal")
    assert context.pillars == ("trilha", "palco") and context.duration_s == 90
    assert context.provenance == {f"editorial.{name}": "channel" for name in EDITORIAL_FIELDS}
    assert not context.legacy


def test_absence_of_a_profile_keeps_the_legacy_editorial_defaults():
    context = EditorialContext.from_effective_config(resolve_effective_config(video=video()))

    assert (context.language, context.audience, context.pillars, context.narrative) == \
        (DEFAULT_LANGUAGE, "", (), "")
    assert (context.cta, context.duration_s) == ("", DEFAULT_DURATION_S)
    assert context.legacy
    assert set(context.provenance.values()) == {"engine_default"}


def test_default_prompt_text_is_unchanged_without_a_profile():
    claims = prompt_claims()
    legacy = build_prompt("ADE 2026", claims, 4)
    context = EditorialContext.from_effective_config(resolve_effective_config(video=video()))

    assert "português do Brasil" in legacy and "Duração alvo" not in legacy
    assert build_prompt("ADE 2026", claims, 4, context=context) == legacy
    assert language_label(DEFAULT_LANGUAGE) == "português do Brasil"
    assert language_label("en-US") == "en-US"  # sem tradução conhecida, o próprio código


def test_channel_language_changes_the_short_prompt():
    claims = prompt_claims()
    pt = EditorialContext.from_effective_config(resolve_effective_config(video=video(), channel=channel(language="pt-BR")))
    en = EditorialContext.from_effective_config(resolve_effective_config(video=video(), channel=channel(language="en-US")))

    pt_prompt, en_prompt = build_prompt("ADE 2026", claims, 4, context=pt), build_prompt("ADE 2026", claims, 4, context=en)
    assert "português do Brasil" in pt_prompt
    assert "en-US" in en_prompt and "português do Brasil" not in en_prompt
    assert pt_prompt != en_prompt


def test_channel_editorial_fields_reach_the_short_prompt():
    context = EditorialContext.from_effective_config(resolve_effective_config(video=video(), channel=channel(
        audience="produtores de eventos", narrative="documental em três atos", pillars=["trilha", "palco"],
        cta="inscreva-se no canal", target_duration_s=90)))

    prompt = build_prompt("ADE 2026", prompt_claims(), 4, context=context)
    for expected in ("Duração alvo ~90s", "produtores de eventos", "documental em três atos", "trilha; palco",
                     "inscreva-se no canal"):
        assert expected in prompt


def test_generate_script_uses_the_context_from_the_injected_resolver(world):
    seed(world)
    config = resolve_effective_config(video=video(), channel=channel(
        language="en-US", audience="produtores de eventos", target_duration_s=90))
    seen: list[str] = []
    gen = GenerateScript(world["videos"], world["snaps"], world["scripts"], Text(good_payload()),
                         CostGuard(world["usage"], 0.0, 15.0), world["usage"],
                         editorial_for=lambda v: seen.append(v.project_id) or config)

    gen.execute(V, 4)
    prompt = gen.text_model.prompts[0]
    assert seen == [P]
    assert "en-US" in prompt and "Duração alvo ~90s" in prompt and "produtores de eventos" in prompt


def test_profile_context_never_relaxes_the_source_requirement(world):
    config = resolve_effective_config(video=video(), channel=channel(language="en-US"))
    gen = GenerateScript(world["videos"], world["snaps"], world["scripts"], Text(good_payload()),
                         CostGuard(world["usage"], 0.0, 15.0), world["usage"],
                         editorial_for=lambda v: config)

    with pytest.raises(SourceRefused):
        gen.execute(V, 4)  # sem fontes: o perfil não inventa fatos
    assert gen.text_model.calls == 0


def test_profile_context_never_relaxes_claim_citation(world):
    seed(world)
    config = resolve_effective_config(video=video(), channel=channel(language="en-US"))
    payload = good_payload()
    for scene in payload["scenes"]:
        scene["claim_ids"] = []
    gen = GenerateScript(world["videos"], world["snaps"], world["scripts"], Text(payload),
                         CostGuard(world["usage"], 0.0, 15.0), world["usage"],
                         editorial_for=lambda v: config)

    with pytest.raises(ScriptRejected, match="claim_ids is required"):
        gen.execute(V, 4)
    assert world["scripts"].saved == []


def test_a_context_from_another_video_is_refused_instead_of_leaking_the_channel(world):
    seed(world)
    other = Video(id="d" * 32, project_id="c" * 32, topic="Outro vídeo", format=VideoFormat.short,
                  status=VideoStatus.IDEA)
    config = resolve_effective_config(video=other, channel=ChannelProfile(
        id="c" * 32, project_id="c" * 32, name="Canal B", language="en-US"))
    gen = GenerateScript(world["videos"], world["snaps"], world["scripts"], Text(good_payload()),
                         CostGuard(world["usage"], 0.0, 15.0), world["usage"],
                         editorial_for=lambda v: config)

    with pytest.raises(ValueError, match="another video"):
        gen.execute(V, 4)
    assert gen.text_model.calls == 0
