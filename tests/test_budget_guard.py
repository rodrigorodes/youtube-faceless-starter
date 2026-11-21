"""Ciclo de vida da operação paga: unidade do guard e wiring dos caminhos pagos reais.

Sem banco nem rede: repositório, provedores e persistência são substituídos por fakes injetados.
A semântica transacional do adaptador PostgreSQL é coberta em `test_paid_operations.py`.
"""
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.budget import (  # noqa: E402
    BeginResult, BudgetDenied, CostConfirmation, CostConfirmationError, OperationInProgress, OperationSettled,
    OperationUncertain, PaidOperationGuard, PaidOperationState, PreEffectFailure,
)
from app.studio.application.editorial import CostGuard, GenerateScript, IngestSource  # noqa: E402
from app.studio.application.ports import ImageResult, RenderQaInputs, TextResult  # noqa: E402
from app.studio.domain.claims import extract_claims  # noqa: E402
from app.studio.domain.contracts import (  # noqa: E402
    Asset, AssetKind, JobStatus, RenderJob, Scene, Script, SourceSnapshot, UsageEntry, Video, VideoFormat, VideoStatus,
)
from app.studio.domain.qa_report import QaCoverage, QaReport  # noqa: E402
from app.studio.domain.media import build_image_prompt  # noqa: E402

V, P = "v" * 32, "p" * 32
ALLOW = ("amsterdam-dance-event.nl",)
SOURCE = ("Amsterdam Dance Event celebrates 30 years with more than 3,600 artists, 1,300 events and 300 venues across the city.\n"
          "Jean-Michel Jarre opens the festival with a concert at AFAS Live on 21 October to mark 50 years of Oxygène.\n")


# ---------------------------------------------------------------- fake persistence


class FakeLedger:
    """Repositório pago em memória: registra a máquina de estados sem tocar em banco."""

    def __init__(self, deny=False, reserved=None):
        self.states = dict(reserved or {})
        self.events = []
        self.settlements = {}
        self.created = []
        self.attempts = {}
        self.deny = deny

    def begin(self, key, video_id, estimate_usd, monthly_limit_usd, video_limit_usd):
        self.events.append(("begin", key, estimate_usd, video_id))
        if self.deny:
            return BeginResult.DENIED
        state = self.states.get(key)
        if state is None:
            self.states[key] = PaidOperationState.RESERVED
            self.attempts[key] = 1
            self.created.append(key)
            return BeginResult.CREATED
        if state is PaidOperationState.RELEASED:
            # liberada = nenhum efeito externo: reabre como nova tentativa, com nova reserva
            self.states[key] = PaidOperationState.RESERVED
            self.attempts[key] += 1
            self.settlements.pop(key, None)
            self.created.append(key)
            return BeginResult.CREATED
        return {PaidOperationState.RESERVED: BeginResult.IN_PROGRESS,
                PaidOperationState.CONFIRMED: BeginResult.CONFIRMED,
                PaidOperationState.UNCERTAIN: BeginResult.UNCERTAIN}[state]

    def confirm(self, key, entry, confirmation):
        assert self.states[key] in (PaidOperationState.RESERVED, PaidOperationState.UNCERTAIN)
        self.states[key] = PaidOperationState.CONFIRMED
        self.settlements[key] = confirmation
        self.events.append(("confirm", key, confirmation.kind, confirmation.amount_usd))

    def release(self, key, reason):
        assert self.states[key] in (PaidOperationState.RESERVED, PaidOperationState.UNCERTAIN)
        self.states[key] = PaidOperationState.RELEASED
        self.events.append(("release", key, reason))

    def mark_uncertain(self, key, reason):
        assert self.states[key] is PaidOperationState.RESERVED
        self.states[key] = PaidOperationState.UNCERTAIN
        self.events.append(("uncertain", key, reason))

    def state(self, key):
        return self.states.get(key)

    def settlement(self, key):
        return self.settlements.get(key)

    def pending_reconciliation(self):
        return []

    def only_key(self):
        return next(iter(self.states))


def guard(ledger, monthly="1", video="1"):
    return PaidOperationGuard(ledger, Decimal(monthly), Decimal(video))


def free_settlement(entry_cost=0.0, provider="fake"):
    entry = UsageEntry(step="text", provider=provider, model="m", cost_usd=entry_cost)
    amount = Decimal(str(entry_cost))
    if amount == 0:
        return entry, CostConfirmation.free(reference=f"provider:{provider}", confirmed_by="studio")
    return entry, CostConfirmation.actual(amount, reference=f"provider:{provider}", confirmed_by="studio")


# ---------------------------------------------------------------- guard states


def test_begin_result_cannot_be_treated_as_boolean():
    for result in BeginResult:
        with pytest.raises(TypeError):
            bool(result)


def test_denied_does_not_execute_the_paid_call():
    ledger, calls = FakeLedger(deny=True), []
    with pytest.raises(BudgetDenied):
        guard(ledger).run("k", V, Decimal("0.5"), lambda: calls.append(1), settle=lambda _: free_settlement())
    assert calls == []
    assert ledger.events == [("begin", "k", Decimal("0.5"), V)]


def test_in_progress_does_not_execute_a_second_call():
    ledger = FakeLedger(reserved={"k": PaidOperationState.RESERVED})
    calls = []
    with pytest.raises(OperationInProgress):
        guard(ledger).run("k", V, Decimal("0.5"), lambda: calls.append(1), settle=lambda _: free_settlement())
    assert calls == []


def test_confirmed_operation_replay_never_executes_again():
    ledger, calls = FakeLedger(), []
    g = guard(ledger)
    g.run("k", V, Decimal("0.5"), lambda: calls.append(1), settle=lambda _: free_settlement(entry_cost=0.5))
    with pytest.raises(OperationSettled):
        g.run("k", V, Decimal("0.5"), lambda: calls.append(1), settle=lambda _: free_settlement(entry_cost=0.5))
    assert calls == [1]
    assert ledger.state("k") is PaidOperationState.CONFIRMED


def test_ambiguous_failure_keeps_the_block_and_requires_reconciliation():
    ledger, calls = FakeLedger(), []
    g = guard(ledger)

    def ambiguous():
        calls.append(1)
        raise RuntimeError("connection reset after the request was sent")

    with pytest.raises(RuntimeError):
        g.run("k", V, Decimal("0.5"), ambiguous, settle=lambda _: free_settlement())
    assert ledger.state("k") is PaidOperationState.UNCERTAIN
    assert ("uncertain", "k", "ambiguous failure: RuntimeError: connection reset after the request was sent") in ledger.events
    with pytest.raises(OperationUncertain):
        g.run("k", V, Decimal("0.5"), ambiguous, settle=lambda _: free_settlement())
    assert calls == [1]


def test_known_pre_effect_failure_releases_the_reservation():
    ledger = FakeLedger()
    g = guard(ledger)

    def refused():
        raise PreEffectFailure("request rejected with HTTP 422 before any generation")

    with pytest.raises(PreEffectFailure):
        g.run("k", V, Decimal("0.5"), refused, settle=lambda _: free_settlement())
    assert ledger.state("k") is PaidOperationState.RELEASED
    assert any(event[0] == "release" for event in ledger.events)


def test_released_operation_can_retry_and_charges_only_once():
    ledger, calls = FakeLedger(), []
    g = guard(ledger)

    def refused():
        calls.append("attempt")
        raise PreEffectFailure("bridge refused the connection before generation")

    with pytest.raises(PreEffectFailure):
        g.run("k", V, Decimal("0.5"), refused, settle=lambda _: free_settlement())
    assert ledger.state("k") is PaidOperationState.RELEASED

    result = g.run("k", V, Decimal("0.5"), lambda: calls.append("call") or "paid output",
                   settle=lambda _: free_settlement(entry_cost=0.42))
    assert result == "paid output"
    assert calls == ["attempt", "call"]  # a segunda tentativa executou de fato
    assert ledger.state("k") is PaidOperationState.CONFIRMED
    assert ledger.attempts["k"] == 2  # nova tentativa, attempt incrementado
    assert [event for event in ledger.events if event[0] == "confirm"] == [("confirm", "k", "ACTUAL", Decimal("0.42"))]
    assert ledger.created == ["k", "k"]  # reserva nova na reabertura

    with pytest.raises(OperationSettled):  # CONFIRMED continua terminal
        g.run("k", V, Decimal("0.5"), lambda: calls.append("again"), settle=lambda _: free_settlement())


def test_confirm_failure_marks_the_operation_uncertain_and_reraises():
    class _ConfirmFails(FakeLedger):
        def confirm(self, key, entry, confirmation):
            raise CostConfirmationError("confirmed amount does not match the recorded provider cost")

    ledger = _ConfirmFails()
    with pytest.raises(CostConfirmationError):
        guard(ledger).run("k", V, Decimal("0.5"), lambda: "paid", settle=lambda _: free_settlement(entry_cost=0.5))
    assert ledger.state("k") is PaidOperationState.UNCERTAIN
    assert ("uncertain", "k", "confirmation failed: CostConfirmationError: confirmed amount does not match the recorded provider cost") in ledger.events


def test_confirm_failure_keeps_the_original_error_when_marking_uncertain_also_fails():
    class _ConfirmAndMarkFail(FakeLedger):
        def confirm(self, key, entry, confirmation):
            raise CostConfirmationError("confirmed amount does not match the recorded provider cost")

        def mark_uncertain(self, key, reason):
            raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable") as info:
        guard(_ConfirmAndMarkFail()).run("k", V, Decimal("0.5"), lambda: "paid",
                                         settle=lambda _: free_settlement(entry_cost=0.5))
    assert isinstance(info.value.__cause__, CostConfirmationError)  # exceção original preservada como causa


def test_confirmed_actual_cost_is_recorded_and_releases():
    ledger = FakeLedger()
    result = guard(ledger).run("k", V, Decimal("0.5"), lambda: {"cost": 0.42},
                               settle=lambda r: free_settlement(entry_cost=r["cost"]))
    assert result == {"cost": 0.42}
    assert ("confirm", "k", "ACTUAL", Decimal("0.42")) in ledger.events
    assert ledger.state("k") is PaidOperationState.CONFIRMED


def test_confirmed_free_releases_without_cost():
    ledger = FakeLedger()
    guard(ledger).run("k", V, Decimal("0"), lambda: "spoken", settle=lambda _: free_settlement(entry_cost=0.0))
    assert ("confirm", "k", "FREE", Decimal("0")) in ledger.events
    assert ledger.state("k") is PaidOperationState.CONFIRMED


def test_success_without_a_confirmable_cost_stays_uncertain():
    ledger = FakeLedger()
    with pytest.raises(OperationUncertain):
        guard(ledger).run("k", V, Decimal("0.5"), lambda: "tokenless", settle=lambda _: None)
    assert ledger.state("k") is PaidOperationState.UNCERTAIN


def test_unconfirmable_settlement_stays_uncertain_and_never_rounds_to_zero():
    ledger = FakeLedger()

    def settle(_):
        raise ValueError("provider cost is not a usable number")

    with pytest.raises(ValueError):
        guard(ledger).run("k", V, Decimal("0.5"), lambda: "ok", settle=settle)
    assert ledger.state("k") is PaidOperationState.UNCERTAIN


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), 0.5, None, "0.5"])
def test_reserve_rejects_invalid_estimates(value):
    with pytest.raises(ValueError):
        guard(FakeLedger()).reserve("k", V, value)


def test_cost_confirmation_validates_kind_amount_and_evidence():
    with pytest.raises(ValueError):
        CostConfirmation.actual(Decimal("0"), reference="invoice", confirmed_by="reviewer")
    with pytest.raises(ValueError):
        CostConfirmation.free(reference="  ", confirmed_by="reviewer")
    with pytest.raises(ValueError):
        CostConfirmation.free(reference="invoice", confirmed_by="")
    with pytest.raises(ValueError):
        CostConfirmation("BOGUS", Decimal("1"), "invoice", "reviewer")


# ---------------------------------------------------------------- paid paths: script


class _Videos:
    def __init__(self, status=VideoStatus.IDEA):
        self.status = status
        self.exists = True

    def get_video(self, video_id):
        return Video(id=V, project_id=P, topic="ADE 2026", format=VideoFormat.short, status=self.status) if self.exists else None


class _Snapshots:
    def __init__(self):
        self.items = []

    def add(self, video_id, url, text):
        snap = SourceSnapshot(id=f"{len(self.items):032x}", video_id=video_id, url=url, content_sha256="a" * 64, text=text)
        self.items.append(snap)
        return snap

    def list(self, video_id):
        return list(self.items)


class _Scripts:
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


class _Usage:
    def __init__(self):
        self.entries = []

    def record(self, video_id, entry):
        self.entries.append(entry)

    def spent_video(self, video_id):
        return 0.0

    def spent_month(self):
        return 0.0


class _Text:
    name, model = "fake", "m"

    def __init__(self, payload, cost=0.0):
        self.payload, self.cost, self.calls = payload, cost, 0

    def cost_estimate(self, prompt):
        return self.cost

    def complete(self, prompt, *, json_schema=None):
        self.calls += 1
        raw = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return TextResult(text=raw, usage=UsageEntry(step="script", provider=self.name, model=self.model, cost_usd=self.cost))


def _good_payload():
    ids = [c.id for c in extract_claims("s" * 32, SOURCE)]
    narrations = ["Eram mais de três mil e seiscentos artistas.", "Jean-Michel Jarre abriu o festival no AFAS Live."]
    return {"scenes": [{"narration": n, "caption": "Legenda", "label": "QUA",
                        "image_prompt": "wide stage with colorful lights and haze", "claim_ids": [ids[i % len(ids)]]}
                       for i, n in enumerate(narrations)] * 2}


def _script_world(cost=0.0):
    videos, scripts, snaps, usage = _Videos(), None, _Snapshots(), _Usage()
    scripts = _Scripts(videos)
    snaps.add(V, "https://amsterdam-dance-event.nl/x", SOURCE)
    return videos, snaps, scripts, usage, _Text(_good_payload(), cost)


def test_generate_script_routes_through_the_paid_guard():
    videos, snaps, scripts, usage, model = _script_world(cost=0.25)
    ledger = FakeLedger()
    gen = GenerateScript(videos, snaps, scripts, model, CostGuard(usage, 0.0, 15.0), usage, paid=guard(ledger))
    gen.execute(V)
    assert model.calls == 1
    assert ledger.state(ledger.only_key()) is PaidOperationState.CONFIRMED
    assert ("confirm", ledger.only_key(), "ESTIMATE", Decimal("0.25")) in ledger.events
    assert usage.entries == []  # o guard é dono da escrita confirmada no ledger


def test_generate_script_replay_does_not_call_the_model_twice():
    videos, snaps, scripts, usage, model = _script_world(cost=0.25)
    ledger = FakeLedger()
    gen = GenerateScript(videos, snaps, scripts, model, CostGuard(usage, 0.0, 15.0), usage, paid=guard(ledger))
    gen.execute(V)
    with pytest.raises(OperationSettled):
        gen.execute(V)
    assert model.calls == 1


def test_generate_script_without_guard_keeps_the_legacy_usage_record():
    videos, snaps, scripts, usage, model = _script_world(cost=0.0)
    GenerateScript(videos, snaps, scripts, model, CostGuard(usage, 0.0, 15.0), usage).execute(V)
    assert len(usage.entries) == 1


# ---------------------------------------------------------------- paid paths: image


class _Assets:
    def __init__(self):
        self.by_key, self.by_id, self.links = {}, {}, {}

    def find(self, key):
        return self.by_key.get(key)

    def add(self, asset):
        self.by_key[asset.cache_key] = self.by_id[asset.id] = asset
        return asset

    def get(self, asset_id):
        return self.by_id.get(asset_id)

    def link_scene(self, video_id, idx, asset_id, image_prompt):
        self.links[idx] = asset_id
        return True


class _Store:
    def put(self, cache_key, data, aspect):
        return f"cache/{cache_key[:2]}/{cache_key}.png"


class _Lock:
    def hold(self, video_id):
        import contextlib
        return contextlib.nullcontext(True)


class _MediaVideos:
    def __init__(self):
        self.status = VideoStatus.STORYBOARDED

    def get_video(self, video_id):
        return Video(id=V, project_id=P, topic="ADE 2026", format=VideoFormat.short, status=self.status)

    def transition_video(self, video_id, expected, new):
        if self.status != expected:
            return False
        self.status = new
        return True


class _MediaScripts:
    def scenes(self, video_id):
        return [Scene(id="0" * 32, video_id=V, idx=0, narration="Narração válida da cena", image_prompt="wide stage with colorful lights",
                      claim_ids=["c"], asset_id=None)]


class _Image:
    name, model = "fake", "m:free"

    def __init__(self, cost=0.05):
        self.cost, self.calls = cost, 0

    def cost_estimate(self, prompt):
        return self.cost

    def generate(self, prompt, *, aspect="9:16"):
        self.calls += 1
        return ImageResult(data=b"img", mime="image/png", license="ai-generated:m", attribution="", source_url="",
                           usage=UsageEntry(step="image", provider=self.name, model=self.model, cost_usd=self.cost))


def test_produce_assets_routes_images_through_the_paid_guard():
    from app.studio.application.media import ProduceAssets

    usage, model = _Usage(), _Image(cost=0.05)
    ledger = FakeLedger()
    produce = ProduceAssets(_MediaVideos(), _MediaScripts(), _Assets(), _Store(), CostGuard(usage, 0.0, 15.0), usage,
                            image_for=lambda project_id: model, lock=_Lock(), paid=guard(ledger))
    produce.execute(V)
    assert model.calls == 1
    assert ("confirm", ledger.only_key(), "ESTIMATE", Decimal("0.05")) in ledger.events
    assert usage.entries == []


# ---------------------------------------------------------------- paid paths: voice


class _RenderVideos:
    def __init__(self):
        self.status = VideoStatus.ASSETS_READY

    def get_video(self, video_id):
        return Video(id=V, project_id=P, topic="ADE 2026", format=VideoFormat.short, status=self.status)


class _RenderScripts:
    TEXTS = ["Primeira narração do vídeo.", "Segunda narração um pouco maior.", "Terceira e última narração."]

    def scenes(self, video_id):
        return [Scene(id=f"{i:032x}", video_id=V, idx=i, narration=t, label="QUA", caption="x",
                      image_prompt="prompt de imagem válido", claim_ids=["c"], asset_id=f"{i:032x}") for i, t in enumerate(self.TEXTS)]


class _RenderAssets:
    def get(self, asset_id):
        return Asset(id=asset_id, kind=AssetKind.image, cache_key=asset_id * 2, path=f"cache/ab/{asset_id}.png",
                     provider="placeholder", model="g", license="CC0")

    def add(self, asset):
        return asset


class _Jobs:
    def __init__(self):
        self.job = RenderJob(id="1" * 32, video_id=V, status=JobStatus.QUEUED, attempt=1, input_hash="a" * 64)

    def get(self, job_id):
        return self.job

    def start(self, job_id):
        self.job = self.job.model_copy(update={"status": JobStatus.RUNNING})
        return True

    def alive(self, job_id):
        return True

    def complete(self, job_id, asset, qa):
        self.job = self.job.model_copy(update={"status": JobStatus.SUCCEEDED, "output_asset_id": asset.id})
        return True

    def fail(self, job_id, error):
        self.error = error


class _Files:
    def __init__(self, tmp):
        self.tmp = tmp

    def work_dir(self, project_id, video_id, job_id):
        path = self.tmp / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def image_path(self, relative):
        return self.tmp / relative

    def publish(self, project_id, video_id, job_id, mp4, srt):
        return f"final-{job_id}.mp4"

    def cleanup(self, work_dir):
        pass


class _Voice:
    name, model = "piper", "local"

    def __init__(self):
        self.calls = []

    def speak(self, text, out_path):
        self.calls.append(text)
        Path(out_path).write_bytes(b"wav")
        return 1.0


class _Renderer:
    name = "fake"

    def render(self, spec, out_path):
        Path(out_path).write_bytes(b"mp4")
        return Path(out_path)

    def qa_inputs(self, spec):
        return RenderQaInputs(plan=object(), descriptors=())  # o QA destes testes é o double _Quality


class _Quality:
    """Porta de QA falsa (o alvo aqui é o guard de custo, não a medição de mídia)."""

    def evaluate(self, plan, *, media_path, narration_path=None, descriptors=(), render_id, checksum):
        return QaReport(render_id=render_id, checksum=checksum, generated_at=datetime.now(timezone.utc),
                        coverage=QaCoverage(status="verified"), checks_run=("render.media_metrics",))


def test_run_render_routes_voice_through_the_paid_guard(tmp_path):
    from app.studio.application.render import RunRender

    usage, voice, ledger = _Usage(), _Voice(), FakeLedger()
    run = RunRender(_RenderVideos(), _RenderScripts(), _RenderAssets(), _Jobs(), _Files(tmp_path),
                    voice_for=lambda project_id: voice, renderer_for=lambda project_id: _Renderer(), quality=_Quality(),
                    paid=guard(ledger, monthly="15", video="15"))
    run.execute("1" * 32)
    assert len(voice.calls) == len(_RenderScripts.TEXTS)
    assert len([e for e in ledger.events if e[0] == "begin"]) == len(_RenderScripts.TEXTS)
    assert all(state is PaidOperationState.CONFIRMED for state in ledger.states.values())
    assert usage.entries == []


# ---------------------------------------------------------------- cost policy: ESTIMATE vs ACTUAL


def test_provider_settlement_never_promotes_an_estimate_to_actual():
    from app.studio.application.budget import ChargeEvidence, provider_settlement

    entry = UsageEntry(step="image", provider="opencode", model="m", cost_usd=0.05)
    _, confirmation = provider_settlement(entry, settled_by="studio:image:opencode")
    assert confirmation.kind == "ESTIMATE"
    assert confirmation.amount_usd == Decimal("0.05")
    assert confirmation.confirmed_by == "studio:image:opencode"


def test_provider_settlement_accepts_actual_only_with_charge_evidence():
    from app.studio.application.budget import ChargeEvidence, provider_settlement

    entry = UsageEntry(step="image", provider="paid", model="m", cost_usd=0.05)
    evidence = ChargeEvidence(Decimal("0.06"), reference="invoice:123", declared_by="billing:adapter")
    charged_entry, confirmation = provider_settlement(entry, settled_by="studio:image:paid", charge=evidence)
    assert confirmation.kind == "ACTUAL"
    assert confirmation.amount_usd == Decimal("0.06")  # vale o valor cobrado, não a estimativa
    assert confirmation.reference == "invoice:123"
    assert confirmation.confirmed_by == "billing:adapter"
    assert charged_entry.cost_usd == 0.06  # o ledger registra o valor cobrado


def test_provider_settlement_requires_an_explicit_actor():
    from app.studio.application.budget import provider_settlement

    entry = UsageEntry(step="text", provider="demo", model="local", cost_usd=0.0)
    with pytest.raises(TypeError):
        provider_settlement(entry)
    with pytest.raises(ValueError):
        provider_settlement(entry, settled_by="   ")


def test_provider_settlement_zero_is_free():
    from app.studio.application.budget import provider_settlement

    entry = UsageEntry(step="voice", provider="piper", model="local", cost_usd=0.0)
    _, confirmation = provider_settlement(entry, settled_by="studio:voice:piper")
    assert confirmation.kind == "FREE"


# ---------------------------------------------------------------- guard: validate / failures


def test_invalid_paid_output_stays_uncertain_not_confirmed():
    ledger = FakeLedger()
    paid = guard(ledger)

    def reject(_):
        raise ValueError("unusable paid output")

    with pytest.raises(ValueError):
        paid.run("k", V, Decimal("0.5"), lambda: "paid", validate=reject, settle=lambda _: free_settlement(0.5))
    assert ledger.state("k") is PaidOperationState.UNCERTAIN
    assert not any(event[0] == "confirm" for event in ledger.events)


def test_pre_effect_failure_during_settlement_releases():
    ledger = FakeLedger()

    def settle(_):
        raise PreEffectFailure("no charge occurred")

    with pytest.raises(PreEffectFailure):
        guard(ledger).run("k", V, Decimal("0.5"), lambda: "ok", settle=settle)
    assert ledger.state("k") is PaidOperationState.RELEASED


def test_unconfirmable_settlement_marks_uncertain():
    ledger = FakeLedger()

    def settle(_):
        raise ValueError("no usable cost")

    with pytest.raises(ValueError):
        guard(ledger).run("k", V, Decimal("0.5"), lambda: "ok", settle=settle)
    assert ledger.state("k") is PaidOperationState.UNCERTAIN


def test_keyboard_interrupt_is_not_swallowed_and_keeps_the_reservation():
    ledger = FakeLedger()

    def interrupted():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        guard(ledger).run("k", V, Decimal("0.5"), interrupted, settle=lambda _: free_settlement())
    assert ledger.state("k") is PaidOperationState.RESERVED  # reconciliação explícita, não UNCERTAIN automático


def test_confirmed_free_operation_can_replay_without_charging():
    ledger = FakeLedger()
    calls = []
    paid = guard(ledger)
    paid.run("k", V, Decimal("0"), lambda: calls.append(1), settle=lambda _: free_settlement(0.0))
    paid.run("k", V, Decimal("0"), lambda: calls.append(1), settle=lambda _: free_settlement(0.0), allow_free_replay=True)
    assert calls == [1, 1]  # reexecutou sem nova reserva e sem cobrança
    assert ledger.created == ["k"]  # nenhuma segunda reserva criada


def test_confirmed_estimate_operation_cannot_replay_for_free():
    ledger = FakeLedger()
    calls = []
    paid = guard(ledger)
    paid.run("k", V, Decimal("0.5"), lambda: calls.append(1), settle=lambda _: free_settlement(0.5))
    with pytest.raises(OperationSettled):
        paid.run("k", V, Decimal("0.5"), lambda: calls.append(1), settle=lambda _: free_settlement(0.5), allow_free_replay=True)
    assert calls == [1]


# ---------------------------------------------------------------- invalid paid results: script and image


def test_invalid_script_after_a_successful_paid_call_stays_uncertain():
    from app.studio.application.editorial import ScriptRejected

    videos, snaps, scripts, usage = _Videos(), _Snapshots(), None, _Usage()
    scripts = _Scripts(videos)
    snaps.add(V, "https://amsterdam-dance-event.nl/x", SOURCE)
    ledger = FakeLedger()
    model = _Text({"scenes": []}, cost=0.25)  # saída inválida (< 2 cenas) mas a chamada paga ocorreu
    gen = GenerateScript(videos, snaps, scripts, model, CostGuard(usage, 0.0, 15.0), usage, paid=guard(ledger))
    with pytest.raises(ScriptRejected):
        gen.execute(V)
    assert model.calls == 1
    assert ledger.state(ledger.only_key()) is PaidOperationState.UNCERTAIN
    assert not any(event[0] == "confirm" for event in ledger.events)


def test_invalid_image_after_a_successful_paid_call_stays_uncertain():
    from app.studio.application.media import AssetRefused, ProduceAssets

    class _BadImage(_Image):
        def generate(self, prompt, *, aspect="9:16"):
            self.calls += 1
            return ImageResult(data=b"img", mime="image/png", license="", attribution="", source_url="",
                               usage=UsageEntry(step="image", provider=self.name, model=self.model, cost_usd=self.cost))

    usage, model, ledger = _Usage(), _BadImage(cost=0.05), FakeLedger()
    produce = ProduceAssets(_MediaVideos(), _MediaScripts(), _Assets(), _Store(), CostGuard(usage, 0.0, 15.0), usage,
                            image_for=lambda project_id: model, lock=_Lock(), paid=guard(ledger))
    with pytest.raises(AssetRefused):
        produce.execute(V)
    assert model.calls == 1
    assert ledger.state(ledger.only_key()) is PaidOperationState.UNCERTAIN
    assert not any(event[0] == "confirm" for event in ledger.events)


# ---------------------------------------------------------------- ideas and voice through the guard


class _IdeaText:
    name, model = "fake", "m"

    def __init__(self, cost=0.10):
        self.cost, self.calls = cost, 0

    def cost_estimate(self, prompt):
        return self.cost

    def complete(self, prompt):
        import re

        self.calls += 1
        topics = re.findall(r"^\d+\. (.+)$", prompt, re.M)
        return TextResult(text=json.dumps({"ideas": [{"topic": t, "relevance": 5, "verifiability": 5, "visual": 5,
                                                       "freshness": 5} for t in topics]}),
                          usage=UsageEntry(step="ideas", provider=self.name, model=self.model, cost_usd=self.cost))


def test_score_ideas_routes_through_the_paid_guard_without_a_video():
    from app.studio.application.ideas import ScoreIdeas

    usage, model, ledger = _Usage(), _IdeaText(0.10), FakeLedger()
    ranked = ScoreIdeas(model, CostGuard(usage, 0.0, 15.0), usage, paid=guard(ledger, monthly="15")).execute(["tema A", "tema B"])
    assert len(ranked) == 2 and model.calls == 1
    assert ("confirm", ledger.only_key(), "ESTIMATE", Decimal("0.1")) in ledger.events
    assert ledger.events[0][3] is None  # operação de projeto, sem vídeo
    assert usage.entries == []


def test_invalid_ideas_after_a_successful_paid_call_stays_uncertain():
    from app.studio.application.ideas import IdeasRejected, ScoreIdeas

    class _BadIdeaText(_IdeaText):
        def complete(self, prompt):
            self.calls += 1
            return TextResult(text=json.dumps({"ideas": [{"topic": "tema não enviado", "relevance": 5,
                                                           "verifiability": 5, "visual": 5, "freshness": 5}]}),
                              usage=UsageEntry(step="ideas", provider=self.name, model=self.model, cost_usd=self.cost))

    usage, model, ledger = _Usage(), _BadIdeaText(0.10), FakeLedger()
    with pytest.raises(IdeasRejected):
        ScoreIdeas(model, CostGuard(usage, 0.0, 15.0), usage, paid=guard(ledger, monthly="15")).execute(["tema A"])
    assert model.calls == 1  # a chamada paga aconteceu
    assert ledger.state(ledger.only_key()) is PaidOperationState.UNCERTAIN
    assert not any(event[0] == "confirm" for event in ledger.events)


class _TwoJobs:
    def __init__(self):
        self.jobs = {f"{job_id}" * 32: RenderJob(id=f"{job_id}" * 32, video_id=V, status=JobStatus.QUEUED, attempt=job_id,
                                                 input_hash="a" * 64)
                     for job_id in (1, 2)}

    def get(self, job_id):
        return self.jobs[job_id]

    def start(self, job_id):
        job = self.jobs[job_id]
        if job.status != JobStatus.QUEUED:
            return False
        self.jobs[job_id] = job.model_copy(update={"status": JobStatus.RUNNING})
        return True

    def alive(self, job_id):
        return True

    def complete(self, job_id, asset, qa):
        self.jobs[job_id] = self.jobs[job_id].model_copy(update={"status": JobStatus.SUCCEEDED})
        return True

    def fail(self, job_id, error):
        self.jobs[job_id] = self.jobs[job_id].model_copy(update={"status": JobStatus.FAILED, "error": error})


class _PaidVoice(_Voice):
    model = "paid"

    def cost_estimate(self, text):
        return 0.10


def test_two_jobs_with_the_same_narration_do_not_charge_twice(tmp_path):
    from app.studio.application.render import RunRender

    usage, voice, ledger, jobs = _Usage(), _PaidVoice(), FakeLedger(), _TwoJobs()
    run = RunRender(_RenderVideos(), _RenderScripts(), _RenderAssets(), jobs, _Files(tmp_path),
                    voice_for=lambda project_id: voice, renderer_for=lambda project_id: _Renderer(), quality=_Quality(),
                    paid=guard(ledger, monthly="15", video="15"))
    run.execute(f"{1}" * 32)
    assert len(voice.calls) == len(_RenderScripts.TEXTS)
    run.execute(f"{2}" * 32)  # retry: a mesma narração já foi paga (ESTIMATE), não pode cobrar de novo
    assert len(voice.calls) == len(_RenderScripts.TEXTS)
    assert jobs.jobs[f"{2}" * 32].status is JobStatus.FAILED
    assert all(state is PaidOperationState.CONFIRMED for state in ledger.states.values())


def test_free_voice_retry_reexecutes_without_a_second_charge(tmp_path):
    from app.studio.application.render import RunRender

    usage, voice, ledger, jobs = _Usage(), _Voice(), FakeLedger(), _TwoJobs()
    run = RunRender(_RenderVideos(), _RenderScripts(), _RenderAssets(), jobs, _Files(tmp_path),
                    voice_for=lambda project_id: voice, renderer_for=lambda project_id: _Renderer(), quality=_Quality(),
                    paid=guard(ledger, monthly="15", video="15"))
    run.execute(f"{1}" * 32)
    run.execute(f"{2}" * 32)
    assert len(voice.calls) == 2 * len(_RenderScripts.TEXTS)  # Piper grátis: reexecuta, sem nova reserva
    assert len(ledger.created) == len(_RenderScripts.TEXTS)
