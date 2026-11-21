"""QA determinístico do plano (RP-030) — política pura, sem FFmpeg.

Prova, por **mutação de evidência**, que um render com defeito (curto demais, mudo, sem
narração, preto, resolução errada, asset ausente) produz achado **blocking** e **não**
aprova no gate da F6, enquanto um render bom fica coberto por `verified` e aprova. E
prova que a ausência de evidência vira cobertura `not_verified` — nunca aprovação por
omissão. A avaliação semântica multimodal é declarada fora (sem provedor); nenhum score
visual é inventado.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.quality import PlanQualityEvaluator  # noqa: E402
from app.studio.domain.asset_resolver import AssetDescriptor  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402
from app.studio.domain.qa_report import (  # noqa: E402
    BlockingFindings,
    CoverageNotVerified,
    QaGateError,
    RenderVersion,
    approve,
)
from app.studio.domain.quality import (  # noqa: E402
    CHECK_ASSET,
    CHECK_AUDIO,
    CHECK_BLACK,
    CHECK_DURATION,
    CHECK_LOUDNESS,
    CHECK_MANIFEST,
    CHECK_MUSIC,
    CHECK_NARRATION,
    CHECK_RESOLUTION,
    MULTIMODAL_EVALUATION,
    QualityEvidence,
    _classify,
    _FAILURE_RULES,
    evaluate_quality,
)
from app.studio.domain.render import MAX_SECONDS  # noqa: E402
from app.studio.domain.render_plan import AssetReference, StyleSnapshot  # noqa: E402
from app.studio.domain.render_plan_builder import StoryboardScene, build_render_plan  # noqa: E402

SHA = "a" * 64
RENDER_ID = "r" * 64
CHECKSUM = "c" * 64
AT = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def make_plan(scene_seconds=(3.0,), fmt=VideoFormat.short, music=True, orphan=False):
    assets = []
    scenes = []
    for index, seconds in enumerate(scene_seconds):
        asset_id = f"asset{index}"
        assets.append(AssetReference(asset_id=asset_id, asset_version=1, uri=f"assets/{index}.png",
                                     content_sha256=SHA, media_type="image", license="CC0"))
        scenes.append(StoryboardScene(scene_id=f"scene{index}", asset_id=asset_id,
                                      narration="Narração do teste automatizado.", speech_seconds=max(0.0, seconds - 0.8),
                                      label="SELO"))
    if orphan:  # manifesto com asset que nenhum shot usa
        assets.append(AssetReference(asset_id="asset-orphan", asset_version=1, uri="assets/orphan.png",
                                     content_sha256=SHA, media_type="image", license="CC0"))
    return build_render_plan(plan_id="plan:test", revision=1, project_id="p", video_id="v", format=fmt,
                             scenes=scenes, assets=assets, style_snapshot=StyleSnapshot(style_id="s", version=1),
                             music=music)


def descriptors_for(plan, *, available=True, license="CC0", width=1080, height=1920):
    refs = {ref.asset_id: ref for ref in plan.asset_manifest}
    return tuple(
        AssetDescriptor(asset_id=ref.asset_id, asset_version=ref.asset_version, uri=ref.uri,
                        content_sha256=ref.content_sha256, media_type=ref.media_type, license=license,
                        available=available, codec="png", width=width, height=height)
        for ref in refs.values()
        if ref.asset_id != "asset-orphan"  # o órfão não é referenciado por shot nenhum
    )


def good_metrics(plan, **overrides):
    expected = plan.timeline.duration_ticks / plan.timeline.ticks_per_second
    fmt = plan.output.format
    width, height = (1080, 1920) if fmt == VideoFormat.short else (1920, 1080)
    base = {"duration_s": round(expected, 3), "width": width, "height": height, "has_audio": True,
            "integrated_lufs": -16.0, "silence_ratio": 0.1, "black_ratio": 0.0,
            "narration_lufs": -18.0, "narration_silence_ratio": 0.1}
    base.update(overrides)
    return base


def evidence(plan, media=None, assets=None, **kw):
    return QualityEvidence(render_id=RENDER_ID, checksum=CHECKSUM, media=media, assets=assets or (),
                           generated_at=AT, **kw)


def gate(report):
    version = RenderVersion(render_id=RENDER_ID, checksum=CHECKSUM)
    return approve(report=report, latest=version, requested=version)


# ------------------------------------------------------------------ vídeo bom

def test_good_render_is_verified_publishable_and_approves_the_latest_version():
    plan = make_plan()
    report = evaluate_quality(plan, evidence(plan, good_metrics(plan), descriptors_for(plan)))
    assert report.coverage.status == "verified"
    assert report.severity_counts == {"blocking": 0, "warning": 0, "info": 0}
    assert report.is_publishable and gate(report).checksum == CHECKSUM


def test_evaluator_port_is_implemented_by_the_pure_application_evaluator():
    plan = make_plan()
    report = PlanQualityEvaluator().evaluate(plan, evidence(plan, good_metrics(plan), descriptors_for(plan)))
    assert report.is_publishable


# ------------------------------------------------------------------ mutação: defeitos de mídia

@pytest.mark.parametrize("overrides,check", [
    ({"duration_s": 1.0}, CHECK_DURATION),          # curto demais (abaixo do mínimo)
    ({"duration_s": 999.0}, CHECK_DURATION),        # acima do limite/diverge do plano
    ({"has_audio": False}, CHECK_AUDIO),            # sem faixa de áudio
    ({"integrated_lufs": None}, CHECK_LOUDNESS),    # mistura muda
    ({"narration_lufs": None}, CHECK_NARRATION),    # narração muda
    ({"black_ratio": 0.9}, CHECK_BLACK),            # preto demais
    ({"width": 1920, "height": 1080}, CHECK_RESOLUTION),  # resolução errada p/ short
])
def test_defective_media_produces_a_blocking_finding_and_is_refused(overrides, check):
    plan = make_plan()
    report = evaluate_quality(plan, evidence(plan, good_metrics(plan, **overrides), descriptors_for(plan)))
    assert report.coverage.status == "verified"  # a evidência foi medida; o defeito é real
    blocking = report.blocking_findings
    assert blocking and any(f.check_id == check for f in blocking)
    with pytest.raises(BlockingFindings):
        gate(report)


def test_wrong_resolution_maps_to_its_own_check():
    plan = make_plan()
    report = evaluate_quality(plan, evidence(plan, good_metrics(plan, width=1080, height=1080), descriptors_for(plan)))
    assert any(f.check_id == CHECK_RESOLUTION for f in report.blocking_findings)


# ------------------------------------------------------------------ falha fechada: sem evidência

def test_missing_metrics_are_not_verified_and_never_approve():
    plan = make_plan()
    partial = {k: v for k, v in good_metrics(plan).items() if k != "black_ratio"}
    report = evaluate_quality(plan, evidence(plan, partial, descriptors_for(plan)))
    assert report.coverage.status == "not_verified" and "black_ratio" in report.coverage.reason
    with pytest.raises(CoverageNotVerified):
        gate(report)


def test_no_media_measured_is_not_verified():
    plan = make_plan()
    report = evaluate_quality(plan, evidence(plan, None, descriptors_for(plan)))
    assert report.coverage.status == "not_verified"


def test_missing_asset_descriptors_is_not_verified():
    plan = make_plan()
    report = evaluate_quality(plan, evidence(plan, good_metrics(plan), ()))
    assert report.coverage.status == "not_verified" and "asset" in report.coverage.reason
    with pytest.raises(CoverageNotVerified):
        gate(report)


def test_an_unresolved_asset_gap_is_reported_even_with_other_descriptors():
    plan = make_plan(scene_seconds=(3.0, 3.0))
    partial = descriptors_for(plan)[:1]  # falta o descriptor da segunda cena
    report = evaluate_quality(plan, evidence(plan, good_metrics(plan), partial))
    assert report.coverage.status == "not_verified" and "asset1" in report.coverage.reason


# ------------------------------------------------------------------ assets

def test_unavailable_asset_is_blocking():
    plan = make_plan()
    unavailable = descriptors_for(plan, available=False)
    report = evaluate_quality(plan, evidence(plan, good_metrics(plan), unavailable))
    assert report.coverage.status == "verified"  # medido; o defeito é do asset
    assert any(f.check_id == CHECK_ASSET for f in report.blocking_findings)
    with pytest.raises(BlockingFindings):
        gate(report)


def test_license_mismatch_with_the_manifest_is_blocking():
    plan = make_plan()
    mismatched = descriptors_for(plan, license="MIT")  # o manifesto declara CC0
    report = evaluate_quality(plan, evidence(plan, good_metrics(plan), mismatched))
    assert any(f.check_id == CHECK_ASSET for f in report.blocking_findings)


# ------------------------------------------------------------------ advisórios (warning/info)

def test_orphan_manifest_asset_is_a_warning_not_a_blocker():
    plan = make_plan(orphan=True)
    report = evaluate_quality(plan, evidence(plan, good_metrics(plan), descriptors_for(plan)))
    assert report.severity_counts["warning"] >= 1
    assert any(f.check_id == CHECK_MANIFEST and f.severity == "warning" for f in report.findings)
    assert report.is_publishable  # aviso não bloqueia


def test_duration_near_the_format_limit_is_a_warning():
    plan = make_plan(scene_seconds=(MAX_SECONDS[VideoFormat.short] * 0.97,))
    report = evaluate_quality(plan, evidence(plan, good_metrics(plan), descriptors_for(plan)))
    assert report.coverage.status == "verified"
    assert any(f.check_id == "render.timeline" and f.severity == "warning" for f in report.findings)
    assert report.is_publishable


def test_silent_music_track_is_declared_as_info():
    plan = make_plan(music=False)
    report = evaluate_quality(plan, evidence(plan, good_metrics(plan), descriptors_for(plan)))
    assert any(f.check_id == CHECK_MUSIC and f.severity == "info" for f in report.findings)
    assert report.is_publishable


# ------------------------------------------------------------------ taxonomia e limites

def test_every_known_failure_message_maps_to_a_declared_check():
    known = {
        "missing metric black_ratio": "render.media_metrics",
        "no audio stream": CHECK_AUDIO,
        "audio is silent (integrated loudness -inf LUFS)": CHECK_LOUDNESS,
        "audio too loud (integrated loudness -3.0 LUFS)": CHECK_LOUDNESS,
        "narration is silent (loudness -inf LUFS)": CHECK_NARRATION,
        "narration has too much silence (90%)": CHECK_NARRATION,
        "too much silence (90% of the video)": "render.silence",
        "too much black (90% of the video)": CHECK_BLACK,
        "duration 1.0s is below the 2.0s": CHECK_DURATION,
        "duration 999.0s is above the 175s limit for short": CHECK_DURATION,
        "duration 5.0s differs from the expected 3.0s": CHECK_DURATION,
        "resolution 1080x1080 is not 1080x1920 for short": CHECK_RESOLUTION,
    }
    rules = {(check, severity) for _, check, severity in _FAILURE_RULES}
    for message, check in known.items():
        assert _classify(message) in rules, message
        assert _classify(message)[0] == check, message


def test_an_unrecognized_failure_is_fail_closed():
    check, severity = _classify("some brand new failure we did not map")
    assert severity == "blocking" and check in {c for _, c, _ in _FAILURE_RULES}


def test_evaluate_qa_failures_are_all_classifiable():
    from app.studio.domain.render import evaluate_qa

    plan = make_plan(scene_seconds=(3.0, 3.0))
    expected = round(plan.timeline.duration_ticks / plan.timeline.ticks_per_second, 3)
    battery = [
        {k: v for k, v in good_metrics(plan).items() if k != "black_ratio"},
        good_metrics(plan, has_audio=False),
        good_metrics(plan, integrated_lufs=None),
        good_metrics(plan, integrated_lufs=-3.0),
        good_metrics(plan, narration_lufs=None),
        good_metrics(plan, narration_silence_ratio=0.9),
        good_metrics(plan, silence_ratio=0.9),
        good_metrics(plan, black_ratio=0.9),
        good_metrics(plan, duration_s=1.0),
        good_metrics(plan, duration_s=999.0),
        good_metrics(plan, width=1080, height=1080),
    ]
    battery = [{**metrics, "expected_s": expected} for metrics in battery]
    prefixes = tuple(prefix for prefix, _, _ in _FAILURE_RULES)
    seen = set()
    for metrics in battery:
        for failure in evaluate_qa(metrics, plan.output.format).failures:
            assert failure.startswith(prefixes), f"mensagem sem check mapeado: {failure!r}"
            seen.add(failure)
    assert len(seen) >= 8  # sanidade: a bateria produziu falhas variadas


def test_multimodal_visual_evaluation_is_declared_out_of_scope():
    assert MULTIMODAL_EVALUATION == "out_of_scope_without_provider"
    plan = make_plan()
    report = evaluate_quality(plan, evidence(plan, good_metrics(plan), descriptors_for(plan)))
    assert not any("visual" in f.check_id or "multimodal" in f.check_id for f in report.findings)


def test_evaluate_quality_rejects_wrong_types():
    plan = make_plan()
    with pytest.raises(TypeError):
        evaluate_quality(plan, "not-evidence")
    with pytest.raises(TypeError):
        evaluate_quality("not-a-plan", evidence(plan, good_metrics(plan), descriptors_for(plan)))


def test_report_is_bound_to_the_render_identity():
    plan = make_plan()
    report = evaluate_quality(plan, evidence(plan, good_metrics(plan), descriptors_for(plan)))
    assert report.render_id == RENDER_ID and report.checksum == CHECKSUM
    other = RenderVersion(render_id="z" * 64, checksum=CHECKSUM)
    with pytest.raises(QaGateError):
        approve(report=report, latest=other, requested=other)
