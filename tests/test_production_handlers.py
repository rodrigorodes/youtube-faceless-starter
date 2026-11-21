"""Handlers do coordenador (D2): ligam as etapas às capacidades reais ou se declaram indisponíveis."""
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.production import (  # noqa: E402
    ApprovalHandler,
    AssetsHandler,
    FactCheckHandler,
    QaHandler,
    RenderHandler,
    RenderQaGate,
    ScriptHandler,
    StageCapabilityUnavailable,
    StageContext,
    StageExecutionFailed,
    StoryboardHandler,
    UnavailableStageHandler,
)
from app.studio.domain.contracts import (  # noqa: E402
    Approval,
    Asset,
    AssetKind,
    JobStatus,
    RenderJob,
    Video,
    VideoFormat,
    VideoStatus,
)
from app.studio.domain.qa_report import QaCoverage, QaFinding, QaReport  # noqa: E402
from app.studio.domain.production_run import ProductionRun, ProductionStage, StageExecution, StageState  # noqa: E402

RUN, VIDEO, JOB, ASSET_ID = "a" * 32, "b" * 32, "c" * 32, "d" * 32
CACHE = "f" * 64


def context(stage):
    run = ProductionRun(run_id=RUN, video_id=VIDEO, idempotency_key="req-1")
    execution = StageExecution(run_id=RUN, stage_id=stage, state=StageState.RUNNING, attempt=2, fencing_token=7,
                               lease_owner="w", lease_expires_at=datetime.now(timezone.utc))
    return StageContext(run=run, execution=execution)


class _Call:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return self.result


class _FactReport:
    def __init__(self, passed, scenes=()):
        self.passed, self.scenes = passed, scenes


def test_script_handler_delegates_and_records_the_version():
    generate = _Call(result=type("S", (), {"version": 4})())
    editorial = type("E", (), {"generate": generate})()
    outcome = ScriptHandler(editorial).execute(context(ProductionStage.SCRIPT))
    assert generate.calls[0][0] == (VIDEO,)
    assert outcome.checkpoint.payload == {"stage": "script", "script_version": 4}
    assert outcome.checkpoint.version == 2  # monotônica pela tentativa


def test_factcheck_handler_fails_closed_when_the_report_does_not_pass():
    flagged = type("F", (), {"idx": 3})()
    editorial = type("E", (), {"fact_check": _Call(result=_FactReport(False, [flagged]))})()
    with pytest.raises(StageExecutionFailed):
        FactCheckHandler(editorial).execute(context(ProductionStage.FACTCHECK))
    passing = type("E", (), {"fact_check": _Call(result=_FactReport(True))})()
    assert FactCheckHandler(passing).execute(context(ProductionStage.FACTCHECK)).checkpoint.payload["passed"] is True


def test_storyboard_and_assets_handlers_use_media():
    storyboard = _Call()
    produce = _Call(result=type("P", (), {"generated": 2, "reused": 1})())
    media = type("M", (), {"storyboard": storyboard, "produce": produce})()
    StoryboardHandler(media).execute(context(ProductionStage.STORYBOARD))
    outcome = AssetsHandler(media).execute(context(ProductionStage.ASSETS))
    assert storyboard.calls == [((VIDEO,), {})]
    assert outcome.checkpoint.payload["generated"] == 2 and outcome.checkpoint.payload["reused"] == 1


class _Jobs:
    def __init__(self, job):
        self.job = job

    def get(self, job_id):
        return self.job

    def latest(self, video_id):
        return self.job

    def approved_output(self, video_id):
        return _asset()

    def latest_output(self, video_id):
        return _asset()


def _job(status=JobStatus.SUCCEEDED):
    return RenderJob(id=JOB, video_id=VIDEO, status=status, output_asset_id=ASSET_ID)


def test_render_handler_runs_inline_and_requires_success():
    start = _Call(result=_job(JobStatus.QUEUED))
    run = _Call()
    handler = RenderHandler(start, run, _Jobs(_job(JobStatus.SUCCEEDED)))
    outcome = handler.execute(context(ProductionStage.RENDER))
    assert start.calls == [((VIDEO,), {})] and run.calls == [((JOB,), {})]
    assert outcome.checkpoint.payload["render_job"] == JOB

    failing = RenderHandler(start, run, _Jobs(_job(JobStatus.FAILED)))
    with pytest.raises(StageExecutionFailed):
        failing.execute(context(ProductionStage.RENDER))


def _asset(asset_id=ASSET_ID, cache=CACHE):
    return Asset(id=asset_id, kind=AssetKind.video, cache_key=cache, path="final.mp4", provider="ffmpeg", model="ffmpeg",
                 license="gerado pelo estúdio")


class _Videos:
    def __init__(self, video):
        self.video = video

    def get_video(self, video_id):
        return self.video


def _video(status=VideoStatus.APPROVED, passed=True, failures=()):
    findings = tuple(QaFinding(finding_id=f"f{index}", check_id="render.media_metrics", category="technical",
                               severity="blocking", evidence=failure, suggested_action="Revisar o render.")
                     for index, failure in enumerate(failures))
    if not passed and not findings:  # reprovado sem falha textual explícita: um bloqueio genérico
        findings = (QaFinding(finding_id="f0", check_id="render.media_metrics", category="technical",
                              severity="blocking", evidence="o QA reprovou o render",
                              suggested_action="Revisar o render."),)
    report = QaReport(render_id=JOB, checksum=CACHE, generated_at=datetime.now(timezone.utc),
                      coverage=QaCoverage(status="verified"), checks_run=("render.media_metrics",), findings=findings)
    return Video(id=VIDEO, project_id="e" * 32, topic="tema", format=VideoFormat.short, status=status, qa_report=report)


def test_qa_handler_requires_a_passing_report():
    handler = QaHandler(_Videos(_video(VideoStatus.RENDERED, passed=True)), _Jobs(_job()))
    assert handler.execute(context(ProductionStage.QA)).checkpoint.payload["qa_passed"] is True

    with pytest.raises(StageExecutionFailed):
        QaHandler(_Videos(_video(VideoStatus.RENDERED, passed=False, failures=["duração curta"])), _Jobs(_job())) \
            .execute(context(ProductionStage.QA))


class _Assets:
    def __init__(self, asset):
        self.asset = asset

    def get(self, asset_id):
        return self.asset if asset_id in (None, self.asset.id) else None


class _Approvals:
    def __init__(self, approval):
        self.approval = approval

    def get(self, video_id):
        return self.approval


def _approved_handler(*, video=None, job=None, latest_asset=None, approved_asset=None, approval=None):
    video = video or _video()
    job = job or _job()
    latest_asset = latest_asset or _asset(cache="a" * 64)
    approved_asset = approved_asset or latest_asset
    jobs = _Jobs(job)
    jobs.approved_output = lambda video_id: latest_asset
    jobs.latest_output = lambda video_id: latest_asset
    gate = RenderQaGate(_Videos(video), jobs, _Assets(approved_asset))
    approval = approval if approval is not None else Approval(video_id=VIDEO, decision="approved", output_asset_id=approved_asset.id)
    return ApprovalHandler(_Videos(video), _Approvals(approval), gate)


def test_approval_handler_pauses_without_a_human_decision():
    approval = Approval(video_id=VIDEO, decision="rejected")
    handler = _approved_handler(approval=approval)
    outcome = handler.execute(context(ProductionStage.APPROVAL))
    assert outcome.request_human is not None and outcome.checkpoint is None


def test_approval_handler_completes_with_the_f6_gate_proof():
    handler = _approved_handler()
    outcome = handler.execute(context(ProductionStage.APPROVAL))
    assert outcome.checkpoint.payload == {"stage": "approval", "render_id": JOB, "checksum": "a" * 64}


def test_approval_handler_refuses_a_superseded_render():
    # O asset aprovado difere do mais recente: uma nova versão surgiu depois da aprovação.
    handler = _approved_handler(latest_asset=_asset(cache="a" * 64), approved_asset=_asset(cache="b" * 64))
    with pytest.raises(StageExecutionFailed, match="QA gate refused"):
        handler.execute(context(ProductionStage.APPROVAL))


def test_approval_handler_refuses_blocking_qa_findings():
    video = _video(passed=False, failures=["frame preto"])
    handler = _approved_handler(video=video)
    with pytest.raises(StageExecutionFailed):
        handler.execute(context(ProductionStage.APPROVAL))


def test_qa_gate_returns_none_without_render_or_report():
    jobs = _Jobs(_job())
    jobs.approved_output = lambda video_id: _asset()
    jobs.latest_output = lambda video_id: _asset()
    assert RenderQaGate(_Videos(_video()), jobs, _Assets(_asset())).report(VIDEO, None) is not None

    class _EmptyJobs(_Jobs):
        def latest(self, video_id):
            return None

    assert RenderQaGate(_Videos(_video()), _EmptyJobs(_job()), _Assets(_asset())).report(VIDEO, None) is None
    assert RenderQaGate(_Videos(_video(passed=True)), _Jobs(_job()), _Assets(_asset())).report(VIDEO, "9" * 32) is not None


def test_unavailable_handler_never_succeeds():
    handler = UnavailableStageHandler(ProductionStage.PUBLISH, "sem publicação")
    assert handler.available is False
    with pytest.raises(StageCapabilityUnavailable):
        handler.execute(context(ProductionStage.PUBLISH))


# ---------- F8: estágio publish real ----------
class _Publish:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def execute(self, **kw):
        self.calls.append(kw)
        return self.outcome


def _publish_outcome(result, detail=None, youtube=None, publication="f" * 32):
    from app.studio.application.publication_execution import PublicationResult, PublicationRun
    from app.studio.domain.contracts import Publication, PublicationStatus
    return PublicationRun(result=result, publication=Publication(id=publication, video_id=VIDEO,
                                                                 status=PublicationStatus.UPLOADED),
                          youtube_video_id=youtube, detail=detail)


def test_publish_handler_completes_only_with_a_confirmed_video_id():
    from app.studio.application.publication_execution import PublicationResult
    from app.studio.application.production import PublishHandler
    publish = _Publish(_publish_outcome(PublicationResult.UPLOADED, youtube="oNQ2KN37sfQ"))
    handler = PublishHandler(publish)
    assert handler.available is True and handler.stage is ProductionStage.PUBLISH
    outcome = handler.execute(context(ProductionStage.PUBLISH))
    assert publish.calls == [{"video_id": VIDEO}]
    assert outcome.checkpoint.payload["youtube_video_id"] == "oNQ2KN37sfQ"
    assert outcome.checkpoint.payload["publication_id"] == "f" * 32


@pytest.mark.parametrize("result,detail", [
    ("IDLE", None), ("RETRY", "HTTP 503"), ("RECONCILE", "unknown"), ("BLOCKED", "QA"), ("DEAD_LETTER", "quota")])
def test_publish_handler_never_turns_an_incomplete_publication_into_success(result, detail):
    from app.studio.application.publication_execution import PublicationResult
    from app.studio.application.production import PublishHandler
    handler = PublishHandler(_Publish(_publish_outcome(PublicationResult(result), detail=detail)))
    with pytest.raises(StageExecutionFailed) as caught:
        handler.execute(context(ProductionStage.PUBLISH))
    assert result in str(caught.value) or (detail or "") in str(caught.value)
