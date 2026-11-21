"""Aplicação long-form (F4-02..F4-06, F4-08) com provedor falso, sem DB nem rede."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.editorial import CostGuard, ScriptRejected  # noqa: E402
from app.studio.application.longform import (  # noqa: E402
    ApproveScriptVersion,
    EditScriptScene,
    GenerateLongScript,
    ScriptApprovalRefused,
    ScriptVersionStale,
    build_long_outline_prompt,
    build_prompt_for_format,
)
from app.studio.application.ports import FactCheckRecord, ScriptRecord, TextResult  # noqa: E402
from app.studio.domain.claims import extract_claims  # noqa: E402
from app.studio.domain.contracts import (  # noqa: E402
    FactCheckReport, Scene, Script, SourceSnapshot, UsageEntry, Video, VideoFormat, VideoStatus,
)
from app.studio.domain.ids import check_id  # noqa: E402
from app.studio.domain.longform import approval_is_current  # noqa: E402

V, P = "v" * 32, "p" * 32
SOURCE = "O canal cresceu 42 por cento no ano passado e esse crescimento mudou o mercado inteiro."


def claim_id():
    return extract_claims("s" * 32, SOURCE)[0].id


def narration(marker: str) -> str:
    return ("ha " * 100).strip() + f" cena {marker}."


class Videos:
    def __init__(self, status=VideoStatus.IDEA, fmt=VideoFormat.long):
        self.status, self.fmt = status, fmt

    def get_video(self, video_id):
        return Video(id=V, project_id=P, topic="Como o dinheiro entra", format=self.fmt, status=self.status)


class Snapshots:
    def __init__(self):
        self.items = []

    def add(self, video_id, url, text):
        snap = SourceSnapshot(id=f"{len(self.items):032x}", video_id=video_id, url=url, content_sha256="a" * 64, text=text)
        self.items.append(snap)
        return snap

    def list(self, video_id):
        return list(self.items)


class Repo:
    """Satisfaz ScriptRepository e LongFormScriptRepository num único objeto."""

    def __init__(self, videos):
        self.videos, self._scenes, self._records = videos, [], []

    def save_and_advance(self, video_id, text, drafts, claim_ids, expected, new):
        return self._save(video_id, text, drafts, claim_ids, None, None, expected, new)

    def save_planned_version(self, video_id, text, drafts, claim_ids, plan, content_hash, expected, new):
        return self._save(video_id, text, drafts, claim_ids, plan, content_hash, expected, new)

    def _save(self, video_id, text, drafts, claim_ids, plan, content_hash, expected, new):
        if self.videos.status != expected:
            return None
        self.videos.status = new
        self._scenes = [Scene(id=f"{i:032x}", video_id=video_id, idx=i, narration=d.narration, caption=d.caption,
                              label=d.label, image_prompt=d.image_prompt, claim_ids=list(d.claim_ids))
                        for i, d in enumerate(drafts)]
        version = len(self._records) + 1
        script = Script(id=f"{version:032x}", video_id=video_id, version=version, text=text, claim_ids=claim_ids)
        self._records.append(ScriptRecord(script=script, plan=plan, content_hash=content_hash, approval=None))
        return script

    def scenes(self, video_id):
        return list(self._scenes)

    def latest(self, video_id):
        return self._records[-1].script if self._records else None

    def list_script_records(self, video_id):
        return list(self._records)

    def approve(self, video_id, version, content_hash, decision, reason, approved_by, approved_at=None):
        from app.studio.domain.longform import ScriptApproval
        if not self._records or self._records[-1].script.version != version:
            return False
        self._records[-1] = ScriptRecord(script=self._records[-1].script, plan=self._records[-1].plan,
                                         content_hash=content_hash,
                                         approval=ScriptApproval(video_id=video_id, script_version=version,
                                                                 content_hash=content_hash, decision=decision,
                                                                 reason=reason, approved_by=approved_by,
                                                                 approved_at=approved_at))
        return True


class Checks:
    def __init__(self):
        self.record = None

    def latest(self, video_id):
        return self.record


class Usage:
    def __init__(self):
        self.entries = []

    def record(self, video_id, entry):
        self.entries.append(entry)

    def spent_video(self, video_id):
        return 0.0

    def spent_month(self):
        return 0.0


class Text:
    name = "fake-long"

    def __init__(self, payloads, cost=0.01):
        self.payloads, self.cost, self.calls, self.prompts = list(payloads), cost, 0, []

    def cost_estimate(self, prompt):
        return self.cost

    def complete(self, prompt, *, json_schema=None):
        self.calls += 1
        self.prompts.append(prompt)
        raw = self.payloads.pop(0) if self.payloads else "{}"
        raw = raw if isinstance(raw, str) else json.dumps(raw)
        return TextResult(text=raw, usage=UsageEntry(step="longform", provider="fake", model="m", cost_usd=self.cost))


def outline_payload(blocks=("hook", "context", "development", "cta"), counts=(2, 3, 5, 2), cid=None):
    cid = cid or claim_id()
    return json.dumps({"chapters": [
        {"title": f"Capitulo {i}", "block": block, "scene_count": count, "references": [cid]}
        for i, (block, count) in enumerate(zip(blocks, counts))
    ]})


def scenes_payload(n, cid=None, marker="{}"):
    cid = cid or claim_id()
    return json.dumps({"scenes": [
        {"narration": narration(marker.format(chr(ord("a") + i)) if "{" in marker else marker), "caption": "Legenda",
         "label": "CEN", "image_prompt": "wide empty stage with colored lights", "claim_ids": [cid]}
        for i in range(n)
    ]})


def world(payload_outline=None, payload_scenes=None, cost=0.01):
    videos, snaps, repo, checks, usage = Videos(), Snapshots(), None, Checks(), Usage()
    repo = Repo(videos)
    cid = claim_id()
    snaps.add(V, "https://example.com/x", SOURCE)
    text = Text([payload_outline or outline_payload(cid=cid), payload_scenes or scenes_payload(12, cid=cid)], cost=cost)
    generator = GenerateLongScript(videos, snaps, repo, text, CostGuard(usage, 1.0, 15.0), usage, repo)
    return {"videos": videos, "snaps": snaps, "repo": repo, "checks": checks, "usage": usage, "text": text,
            "generator": generator, "cid": cid}


# ---------- prompts separados (F4-02) ----------
def test_short_and_long_prompts_are_distinct_constructions():
    cid = claim_id()
    claims = extract_claims("s" * 32, SOURCE)
    short = build_prompt_for_format(VideoFormat.short, "tema", claims, 6)
    long = build_prompt_for_format(VideoFormat.long, "tema", claims, 6, target_seconds=480, words_per_minute=150)
    assert "vídeo curto" in short and "capítulos" not in short
    assert "capítulos" in long and "gancho" in long and "hook|context|development|payoff|cta" in long
    assert long == build_long_outline_prompt("tema", claims, 480, 150)


# ---------- geração em duas passagens (F4-04) ----------
def test_long_generation_is_two_passages_and_persists_plan_and_hash():
    w = world()
    result = w["generator"].execute(V)
    assert w["text"].calls == 2  # plano e cenas
    assert result.scene_count == 12
    assert 400 <= result.estimated_duration_seconds <= 560
    assert result.cost_usd == pytest.approx(0.02)
    assert [c.block.value for c in result.plan.chapters] == ["hook", "context", "development", "cta"]
    records = w["repo"].list_script_records(V)
    assert len(records) == 1 and records[0].plan is not None
    assert len(records[0].content_hash) == 64
    assert records[0].approval is None


def test_long_generation_rejects_plan_without_hook():
    w = world(payload_outline=outline_payload(blocks=("context", "development", "cta"), counts=(4, 6, 2)))
    with pytest.raises(ScriptRejected):
        w["generator"].execute(V)
    assert w["repo"].list_script_records(V) == []


def test_long_generation_rejects_script_with_invented_number():
    bad = json.dumps({"scenes": [
        {"narration": "O canal cresceu 9999 por cento no ano passado e mudou tudo.", "caption": "Legenda",
         "label": "CEN", "image_prompt": "wide empty stage with colored lights", "claim_ids": [claim_id()]}
        for _ in range(12)
    ]})
    w = world(payload_scenes=bad)
    with pytest.raises(ScriptRejected):
        w["generator"].execute(V)
    assert w["repo"].list_script_records(V) == []


# ---------- aprovação por versão/hash (F4-06) ----------
def _approve(w, version, content_hash):
    approver = ApproveScriptVersion(w["videos"], w["snaps"], w["repo"], w["repo"], checks=w["checks"])
    return approver.execute(V, version=version, content_hash=content_hash, approved_by="operador")


def test_approval_requires_fact_check_of_the_version():
    w = world()
    result = w["generator"].execute(V)
    with pytest.raises(ScriptApprovalRefused):
        _approve(w, result.script.version, next(r.content_hash for r in w["repo"].list_script_records(V)))
    w["checks"].record = FactCheckRecord(FactCheckReport(passed=True), result.script.version)
    approval = _approve(w, result.script.version, next(r.content_hash for r in w["repo"].list_script_records(V)))
    assert approval.decision == "approved" and approval.script_version == 1


def test_approval_refuses_a_stale_hash():
    w = world()
    result = w["generator"].execute(V)
    w["checks"].record = FactCheckRecord(FactCheckReport(passed=True), result.script.version)
    with pytest.raises(ScriptVersionStale):
        _approve(w, 1, "e" * 64)


# ---------- edição invalida só o que depende (F4-08) ----------
def test_edit_creates_another_version_and_invalidates_the_approval():
    w = world()
    result = w["generator"].execute(V)
    w["checks"].record = FactCheckRecord(FactCheckReport(passed=True), result.script.version)
    approved_hash = next(r.content_hash for r in w["repo"].list_script_records(V))
    approval = _approve(w, 1, approved_hash)
    assert approval_is_current(approval, version=1, content_hash=approved_hash)

    editor = EditScriptScene(w["videos"], w["snaps"], w["repo"], w["repo"])
    edited = editor.execute(V, 0, narration("editada"), expected_version=1)
    assert edited.script.version == 2

    records = w["repo"].list_script_records(V)
    assert [r.script.version for r in records] == [1, 2]
    assert records[0].approval is not None  # histórico preservado
    assert records[1].approval is None
    assert records[1].content_hash != approved_hash
    # a aprovação da v1 não vale mais para a v2 (é outra versão e outro hash)
    assert not approval_is_current(records[0].approval, version=2, content_hash=records[1].content_hash)
    # fontes intactas: editar roteiro não reescreve nem apaga a origem
    assert len(w["snaps"].list(V)) == 1
    # fact-check da v1 continua apontando para a v1 (não é transferido para a v2)
    assert w["checks"].record.script_version == 1


def test_edit_requires_the_latest_version():
    w = world()
    result = w["generator"].execute(V)
    editor = EditScriptScene(w["videos"], w["snaps"], w["repo"], w["repo"])
    with pytest.raises(ScriptVersionStale):
        editor.execute(V, 0, narration("x"), expected_version=result.script.version + 1)
