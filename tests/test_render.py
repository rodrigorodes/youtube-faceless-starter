import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.editorial import StateConflict, VideoNotFound  # noqa: E402
from app.studio.application.ports import RenderQaInputs  # noqa: E402
from app.studio.application.render import GetRender, GetRenderFile, RenderRefused, RunRender, StartRender  # noqa: E402
from app.studio.application.use_cases import ServiceUnavailable  # noqa: E402
from app.studio.domain.contracts import (  # noqa: E402
    Asset, AssetKind, JobStatus, RenderJob, Scene, Video, VideoFormat, VideoStatus,
)
from app.studio.domain.qa_report import (  # noqa: E402
    BlockingFindings, QaCoverage, QaFinding, QaReport, RenderVersion, approve, blocking_evidence,
)
from app.studio.domain.render import MAX_SECONDS, scene_length  # noqa: E402

S = VideoStatus
V, P = "v" * 32, "p" * 32
TEXTS = ["Primeira narração do vídeo curto.", "Segunda narração, um pouco mais longa que a anterior.", "Terceira e última narração."]


class Videos:
    def __init__(self, status=S.ASSETS_READY, fmt=VideoFormat.short, style_id=None):
        self.status, self.fmt, self.exists, self.style_id = status, fmt, True, style_id

    def get_video(self, video_id):
        return Video(id=V, project_id=P, topic="ADE 2026", format=self.fmt, status=self.status,
                     style_id=self.style_id) if self.exists else None


class Scripts:
    def __init__(self, linked=True, texts=TEXTS):
        self.linked, self.texts = linked, texts

    def scenes(self, video_id):
        return [Scene(id=f"{i:032x}", video_id=V, idx=i, narration=t, label="QUA", caption="x", image_prompt="prompt de imagem válido",
                      claim_ids=["c"], asset_id=f"{i:032x}" if self.linked else None) for i, t in enumerate(self.texts)]


class Assets:
    def __init__(self):
        self.added = []

    def get(self, asset_id):
        return Asset(id=asset_id, kind=AssetKind.image, cache_key=asset_id * 2, path=f"cache/ab/{asset_id}.png", provider="placeholder",
                     model="g", license="CC0")

    def add(self, asset):
        self.added.append(asset)
        return asset


class Jobs:
    def __init__(self, videos):
        self.videos, self.jobs, self.calls = videos, {}, []
        self.fail_complete = False
        self.qa = None
        self.output = None
        self.alive_flag = True
        self.fail_raises = False

    def enqueue(self, video_id, input_hash):
        for job in self.jobs.values():
            if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                return job, False
        job = RenderJob(id=f"{len(self.jobs) + 1:032x}", video_id=video_id, status=JobStatus.QUEUED, attempt=len(self.jobs) + 1, input_hash=input_hash)
        self.jobs[job.id] = job
        return job, True

    def get(self, job_id):
        return self.jobs.get(job_id)

    def latest(self, video_id):
        return list(self.jobs.values())[-1] if self.jobs else None

    def start(self, job_id):
        job = self.jobs[job_id]
        if job.status != JobStatus.QUEUED:
            return False
        self.jobs[job_id] = job.model_copy(update={"status": JobStatus.RUNNING})
        return True

    def alive(self, job_id):
        return self.alive_flag

    def latest_output(self, video_id):
        return self.output

    def fail(self, job_id, error):
        if self.fail_raises:
            raise ConnectionError("banco caiu")
        self.last_error = error
        self.jobs[job_id] = self.jobs[job_id].model_copy(update={"status": JobStatus.FAILED, "error": error})

    def complete(self, job_id, asset, qa):
        if self.fail_complete:
            return False
        self.qa = qa
        self.output = asset
        self.jobs[job_id] = self.jobs[job_id].model_copy(update={"status": JobStatus.SUCCEEDED, "output_asset_id": asset.id})
        self.videos.status = S.AWAITING_APPROVAL if qa.is_publishable else S.RENDERED
        return True


class Files:
    def __init__(self, tmp):
        self.tmp, self.published, self.cleaned = tmp, [], []

    def image_path(self, relative):
        return self.tmp / relative

    def work_dir(self, project_id, video_id, job_id):
        d = self.tmp / "work" / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def publish(self, project_id, video_id, job_id, mp4, srt):
        self.published.append((mp4.read_bytes(), srt))
        self.job_ids = getattr(self, "job_ids", []) + [job_id]
        return f"projects/{project_id}/videos/{video_id}/final-{job_id}.mp4"

    def resolve(self, relative, kind):
        return self.tmp / relative if kind == "mp4" else self.tmp / relative.replace(".mp4", ".srt")

    def prune(self, project_id, video_id, keep):
        self.pruned = getattr(self, "pruned", []) + [keep]

    def cleanup(self, work_dir):
        self.cleaned.append(work_dir)


class Voice:
    name = "fake"

    def __init__(self, seconds=2.0, fail_on=None):
        self.seconds, self.fail_on, self.calls = seconds, fail_on, []

    def speak(self, text, out_path):
        self.calls.append(text)
        if self.fail_on == len(self.calls):
            raise RuntimeError("voz caiu")
        Path(out_path).write_bytes(b"wav")
        return self.seconds


class Renderer:
    name = "fake"

    def __init__(self, fail=False):
        self.fail, self.specs = fail, []

    def render(self, spec, out_path):
        self.specs.append(spec)
        if self.fail:
            raise RuntimeError("ffmpeg falhou")
        Path(out_path).write_bytes(b"mp4")
        return Path(out_path)

    def qa_inputs(self, spec):
        # O porteiro de QA destes testes é o double `Quality`: o plano não é inspecionado aqui.
        return RenderQaInputs(plan=object(), descriptors=())


class Quality:
    """Porta de QA falsa: registra o que o loop entrega e devolve um relatório novo da F6.

    Prova a fiação do loop (identidade do render, caminho da mídia e da narração) sem medir
    mídia — a medição real é provada em ``test_render_quality_e2e``.
    """

    def __init__(self, failures=()):
        self.failures, self.calls = list(failures), []

    def evaluate(self, plan, *, media_path, narration_path=None, descriptors=(), render_id, checksum):
        self.calls.append({"media": media_path, "narration": narration_path, "render_id": render_id, "checksum": checksum})
        findings = tuple(QaFinding(finding_id=f"f{index}", check_id="render.audio_stream", category="technical",
                                   severity="blocking", evidence=failure, suggested_action="Revisar o render.")
                         for index, failure in enumerate(self.failures))
        return QaReport(render_id=render_id, checksum=checksum, generated_at=datetime.now(timezone.utc),
                        coverage=QaCoverage(status="verified"), checks_run=("render.media_metrics", "render.audio_stream"), findings=findings)


def world(tmp, status=S.ASSETS_READY, **kw):
    videos = Videos(status, **kw)
    return {"videos": videos, "scripts": Scripts(), "assets": Assets(), "jobs": Jobs(videos), "files": Files(tmp), "enq": []}


def starter(w):
    return StartRender(w["videos"], w["scripts"], w["assets"], w["jobs"], enqueue=w["enq"].append)


def runner(w, voice=None, renderer=None, quality=None):
    voice, renderer = voice or Voice(), renderer or Renderer()
    quality = quality or Quality()
    return RunRender(w["videos"], w["scripts"], w["assets"], w["jobs"], w["files"], voice_for=lambda p: voice, renderer_for=lambda p: renderer,
                     quality=quality), voice, renderer


# ---------- start ----------
def test_start_creates_a_queued_job_enqueues_it_once_and_is_idempotent(tmp_path):
    w = world(tmp_path)
    job = starter(w).execute(V)
    assert job.status == JobStatus.QUEUED and w["enq"] == [job.id] and len(job.input_hash) == 64
    again = starter(w).execute(V)
    assert again.id == job.id and w["enq"] == [job.id]  # um job ativo por vídeo: não enfileira de novo


@pytest.mark.parametrize("status", [S.IDEA, S.SCRIPTED, S.FACT_CHECKED, S.STORYBOARDED, S.AWAITING_APPROVAL, S.APPROVED, S.FAILED])
def test_start_needs_assets_ready_or_rendered(tmp_path, status):
    w = world(tmp_path, status)
    with pytest.raises(StateConflict):
        starter(w).execute(V)
    assert w["jobs"].jobs == {} and w["enq"] == []


def test_rerender_is_allowed_from_rendered(tmp_path):
    assert starter(world(tmp_path, S.RENDERED)).execute(V).status == JobStatus.QUEUED


def test_start_refuses_scenes_without_asset_unknown_video_or_no_scenes(tmp_path):
    w = world(tmp_path)
    w["scripts"].linked = False
    with pytest.raises(StateConflict, match="asset"):
        starter(w).execute(V)
    w = world(tmp_path)
    w["scripts"].texts = []
    with pytest.raises(StateConflict, match="scenes"):
        starter(w).execute(V)
    w = world(tmp_path)
    w["videos"].exists = False
    with pytest.raises(VideoNotFound):
        starter(w).execute(V)


def test_input_hash_follows_the_content(tmp_path):
    a, b, c = world(tmp_path), world(tmp_path), world(tmp_path)
    b["scripts"].texts = TEXTS[:2]
    c["videos"].fmt = VideoFormat.long
    ha, hb, hc = (starter(x).execute(V).input_hash for x in (a, b, c))
    assert len({ha, hb, hc}) == 3 and ha == starter(world(tmp_path)).execute(V).input_hash


# ---------- run ----------
def test_run_carries_the_resolved_style_into_the_render_spec(tmp_path):
    from app.studio.domain.render_plan import StyleSnapshot
    from app.studio.domain.visual_style import ResolvedStyle
    w = world(tmp_path)
    w["videos"].style_id = "d" * 32  # override do vídeo (VS-02b): precisa chegar ao resolvedor
    job = starter(w).execute(V)
    run, _, renderer = runner(w)
    seen = []
    style = ResolvedStyle(snapshot=StyleSnapshot(style_id="canal-1", version=7),
                          motion=("zoom_in", "zoom_out"), music={"bpm": 90})
    # VS-05c: o resolvedor recebe o **vídeo** (não só o project_id) — é assim que o override chega.
    run.style_for = lambda video: seen.append(video) or style
    run.execute(job.id)
    assert [v.style_id for v in seen] == ["d" * 32] and seen[0].project_id == P
    assert renderer.specs[0].style == style


def test_run_without_a_style_resolver_leaves_the_spec_style_unset(tmp_path):
    w = world(tmp_path)
    job = starter(w).execute(V)
    run, _, renderer = runner(w)
    run.execute(job.id)
    assert renderer.specs[0].style is None  # sem canal a referenciar, o renderer cai no bundle neutro


def test_run_success_passes_everything_to_renderer_and_advances(tmp_path):
    w = world(tmp_path)
    job = starter(w).execute(V)
    run, voice, renderer = runner(w)
    run.execute(job.id)
    spec = renderer.specs[0]
    assert voice.calls == TEXTS and len(spec.images) == 3 and spec.images[0] == tmp_path / f"cache/ab/{0:032x}.png"
    assert spec.scene_seconds == [scene_length(2.0)] * 3 and len(spec.speech_wavs) == 3 and spec.format == VideoFormat.short and spec.music is True
    assert spec.cues and all(c.end > c.start for c in spec.cues) and spec.cues[0].start >= spec.scene_seconds[0] * 0 + 0.3 - 1e-9
    assert spec.disclosure == "Ilustração gerada por IA"
    assert w["jobs"].jobs[job.id].status == JobStatus.SUCCEEDED and w["videos"].status == S.AWAITING_APPROVAL and w["jobs"].qa.is_publishable
    assert w["files"].published[0][0] == b"mp4" and "-->" in w["files"].published[0][1] and w["files"].cleaned
    assert w["assets"].added[0].kind == AssetKind.video and w["assets"].added[0].path.endswith(f"final-{job.id}.mp4")
    assert w["files"].pruned and w["files"].pruned[-1] == w["assets"].added[0].path  # só o arquivo atual sobrevive
    # a identidade que o QA gravou é a mesma que a publicação reutiliza (job + checksum do asset)
    assert w["jobs"].qa.render_id == job.id and w["jobs"].qa.checksum == w["assets"].added[0].cache_key


def test_qa_failure_keeps_video_rendered_with_the_report(tmp_path):
    w = world(tmp_path)
    job = starter(w).execute(V)
    quality = Quality(failures=["audio is silent (integrated loudness None LUFS)"])
    run, *_ = runner(w, quality=quality)
    run.execute(job.id)
    assert w["jobs"].jobs[job.id].status == JobStatus.SUCCEEDED and w["videos"].status == S.RENDERED
    assert not w["jobs"].qa.is_publishable and any("silent" in f for f in blocking_evidence(w["jobs"].qa))
    assert quality.calls[0]["media"].name == "final.mp4"


def test_too_long_video_fails_before_rendering(tmp_path):
    w = world(tmp_path)
    job = starter(w).execute(V)
    run, voice, renderer = runner(w, voice=Voice(seconds=MAX_SECONDS[VideoFormat.short] / 2))
    run.execute(job.id)
    failed = w["jobs"].jobs[job.id]
    assert failed.status == JobStatus.FAILED and "limit" in failed.error and renderer.specs == [] and w["videos"].status == S.ASSETS_READY


@pytest.mark.parametrize("kind", ["voice", "renderer"])
def test_technical_failure_marks_job_failed_and_leaves_state(tmp_path, kind):
    w = world(tmp_path)
    job = starter(w).execute(V)
    run, *_ = runner(w, voice=Voice(fail_on=2) if kind == "voice" else None, renderer=Renderer(fail=True) if kind == "renderer" else None)
    run.execute(job.id)
    failed = w["jobs"].jobs[job.id]
    assert failed.status == JobStatus.FAILED and failed.error and w["videos"].status == S.ASSETS_READY and w["files"].cleaned and w["files"].published == []


def test_run_is_skipped_when_job_is_not_queued(tmp_path):
    w = world(tmp_path)
    job = starter(w).execute(V)
    run, voice, _ = runner(w)
    run.execute(job.id)
    run.execute(job.id)  # já SUCCEEDED
    assert len(voice.calls) == 3
    run.execute("0" * 32)  # inexistente: não explode


def test_state_changed_during_render_fails_the_job(tmp_path):
    w = world(tmp_path)
    job = starter(w).execute(V)
    w["jobs"].fail_complete = True
    run, *_ = runner(w)
    run.execute(job.id)
    assert w["jobs"].jobs[job.id].status == JobStatus.FAILED and "state" in w["jobs"].jobs[job.id].error


def test_stock_images_change_the_on_screen_disclosure(tmp_path):
    w = world(tmp_path)
    original = w["assets"].get
    w["assets"].get = lambda i: original(i).model_copy(update={"provider": "stock", "license": "Pexels License"})
    job = starter(w).execute(V)
    run, _, renderer = runner(w)
    run.execute(job.id)
    assert renderer.specs[0].disclosure == "Imagens ilustrativas"


def test_get_render_returns_latest_job_and_qa(tmp_path):
    w = world(tmp_path)
    assert GetRender(w["videos"], w["jobs"]).execute(V) == (None, None)
    job = starter(w).execute(V)
    found, qa = GetRender(w["videos"], w["jobs"]).execute(V)
    assert found.id == job.id and qa is None
    w["videos"].exists = False
    with pytest.raises(VideoNotFound):
        GetRender(w["videos"], w["jobs"]).execute(V)


# ---------- achados da revisão ----------
def test_silent_narration_fails_qa_even_if_the_mix_has_music(tmp_path):
    w = world(tmp_path)
    job = starter(w).execute(V)
    quality = Quality(failures=["narration is silent (loudness None LUFS)"])
    run, *_ = runner(w, quality=quality)
    run.execute(job.id)
    assert not w["jobs"].qa.is_publishable and any("narration" in f for f in blocking_evidence(w["jobs"].qa)) and w["videos"].status == S.RENDERED
    # o loop mede a narração **isolada** (a trilha musical enche a mistura final)
    assert quality.calls[0]["narration"] is not None and quality.calls[0]["narration"].name == "narration.wav"


def test_run_never_raises_even_when_recording_the_failure_fails(tmp_path):
    w = world(tmp_path)
    job = starter(w).execute(V)
    w["jobs"].fail_raises = True
    run, *_ = runner(w, renderer=Renderer(fail=True))
    run.execute(job.id)  # não pode levantar (a exceção iria para um Future que ninguém lê)
    assert w["files"].cleaned


def test_the_loop_report_is_what_the_gate_blocks_or_approves(tmp_path):
    """Mutação pela raiz: o relatório que o gate da F6 vê é o que o loop persistiu.

    Um render bom aprova; um render com defeito (achado ``blocking`` do loop) é bloqueado —
    sem segunda medição e sem regenerar o relatório no gate.
    """
    good = world(tmp_path)
    good_job = starter(good).execute(V)
    run, *_ = runner(good, quality=Quality())
    run.execute(good_job.id)
    version = RenderVersion(render_id=good["jobs"].qa.render_id, checksum=good["jobs"].qa.checksum)
    assert approve(report=good["jobs"].qa, latest=version, requested=version).checksum == version.checksum

    bad = world(tmp_path)
    bad_job = starter(bad).execute(V)
    broken = Quality(failures=["audio is silent (integrated loudness None LUFS)"])
    run_bad, *_ = runner(bad, quality=broken)
    run_bad.execute(bad_job.id)
    version_bad = RenderVersion(render_id=bad["jobs"].qa.render_id, checksum=bad["jobs"].qa.checksum)
    with pytest.raises(BlockingFindings):
        approve(report=bad["jobs"].qa, latest=version_bad, requested=version_bad)


def test_run_does_not_raise_when_the_repository_is_down_at_the_start(tmp_path):
    w = world(tmp_path)
    job = starter(w).execute(V)
    w["jobs"].get = lambda job_id: (_ for _ in ()).throw(ConnectionError("banco caiu"))
    run, *_ = runner(w)
    run.execute(job.id)


def test_enqueue_failure_marks_the_job_failed_and_reports_unavailable(tmp_path):
    w = world(tmp_path)
    def boom(job_id):
        raise RuntimeError("executor encerrado")
    starter_ = StartRender(w["videos"], w["scripts"], w["assets"], w["jobs"], enqueue=boom)
    with pytest.raises(ServiceUnavailable):
        starter_.execute(V)
    assert list(w["jobs"].jobs.values())[0].status == JobStatus.FAILED
    assert starter(w).execute(V).status == JobStatus.QUEUED  # o vídeo não ficou travado


def test_nothing_is_published_when_the_job_lost_ownership(tmp_path):
    w = world(tmp_path)
    job = starter(w).execute(V)
    w["jobs"].alive_flag = False
    run, *_ = runner(w)
    run.execute(job.id)
    assert w["files"].published == [] and w["jobs"].jobs[job.id].status == JobStatus.FAILED


def test_error_text_does_not_leak_the_work_directory(tmp_path):
    w = world(tmp_path)
    job = starter(w).execute(V)
    class Leaky(Renderer):
        def render(self, spec, out_path):
            raise RuntimeError(f"ffmpeg failed: cannot open {spec.work_dir}/scene_000.mp4")
    run, *_ = runner(w, renderer=Leaky())
    run.execute(job.id)
    error = w["jobs"].jobs[job.id].error
    assert str(tmp_path) not in error and "<work>" in error


def test_file_is_resolved_from_the_latest_output_asset_not_from_a_fixed_name(tmp_path):
    w = world(tmp_path, S.AWAITING_APPROVAL)
    reader = GetRenderFile(w["videos"], w["jobs"], w["files"])
    assert reader.execute(V, "mp4") is None  # ainda sem asset de saída
    w["jobs"].output = Asset(id="9" * 32, kind=AssetKind.video, cache_key="d" * 64, path="projects/p/videos/v/final-abc.mp4", provider="ffmpeg", model="ffmpeg", license="g")
    assert reader.execute(V, "mp4") == tmp_path / "projects/p/videos/v/final-abc.mp4" and reader.execute(V, "srt").name == "final-abc.srt"
    for status in (S.ASSETS_READY, S.FAILED, S.IDEA):
        w["videos"].status = status
        assert reader.execute(V, "mp4") is None
