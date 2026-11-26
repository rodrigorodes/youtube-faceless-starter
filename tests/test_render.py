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
V, P = "1" * 32, "2" * 32  # ids hexadecimais válidos: a configuração efetiva (F03) os valida
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


def test_run_resolves_the_voice_from_the_video_not_the_project(tmp_path):
    """VS-06: o resolvedor de voz recebe o **vídeo** (como o de estilo), para o estilo do canal/override decidir."""
    w = world(tmp_path)
    w["videos"].style_id = "d" * 32
    job = starter(w).execute(V)
    run, _, _ = runner(w)
    seen = []
    run.voice_for = lambda video: seen.append(video) or Voice()
    run.execute(job.id)
    assert [v.style_id for v in seen] == ["d" * 32] and seen[0].project_id == P


def test_the_effective_voice_is_the_same_one_that_speaks_and_is_registered(tmp_path):
    """VS-06 trava a "duas verdades": com voz de estilo, a identidade do cache/ledger (e do spec)
    é o **mesmo** modelo efetivo que a síntese usa."""
    from app.studio.application.render import _voice_identity

    class StyleVoice(Voice):
        name = "piper"
        model = "pt_BR-jeff-medium"  # a voz efetiva resolvida (estilo > projeto > default)

    w = world(tmp_path)
    job = starter(w).execute(V)
    run, _, renderer = runner(w, voice=StyleVoice())
    seen = []
    original = run._cached_narration
    run._cached_narration = lambda scene, voice_id, entries: (seen.append(voice_id), original(scene, voice_id, entries))[1]
    run.execute(job.id)
    identity = _voice_identity(StyleVoice())
    assert identity == "piper:pt_BR-jeff-medium"
    assert seen == [identity] * len(TEXTS)          # o cache consulta pela identidade efetiva
    assert renderer.specs[0].voice_id == identity   # o plano registra a mesma identidade


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


# ---------- F03.T03: uma configuração efetiva congelada governa voz e plano ----------

STYLE_ID = "a" * 32


def frozen_config(style_id=STYLE_ID, params=None, with_style=True):
    """Configuração efetiva real (F03.T01) para o vídeo destes testes — sem canal/perfil."""
    from app.studio.domain.effective_config import resolve_effective_config
    from app.studio.domain.visual_style import VisualStyle

    video = Video(id=V, project_id=P, topic="ADE 2026", format=VideoFormat.short,
                  status=S.ASSETS_READY, style_id=style_id if with_style else None)
    styles = {STYLE_ID: VisualStyle(id=STYLE_ID, name="F03", params=dict(params or {}))}
    return resolve_effective_config(video=video, channel=None,
                                    lookup_style=lambda sid: styles.get(sid))


class ModelVoice(Voice):
    name = "piper"


class ConfigStore:
    """Leitura do snapshot do run (a porta `ProductionRunConfigStore`, em memória)."""

    def __init__(self, configs):
        self.configs, self.reads = dict(configs), []

    def run_config(self, run_id):
        self.reads.append(run_id)
        return self.configs.get(run_id)


def test_the_same_frozen_config_feeds_the_voice_and_the_render_plan(tmp_path):
    w = world(tmp_path)
    config = frozen_config(params={"voice": {"model": "pt_BR-jeff-medium"},
                                   "music": {"bpm": 90},
                                   "motion": ["zoom_in", "pan_right"],
                                   "caption": {"font_size": 62},
                                   "palette": {"accent": "#ff00aa"}})
    job = starter(w).execute(V)
    seen_voice, seen_style, calls = [], [], []

    def voice_for_config(video, cfg):
        from app.studio.application.render import _voice_identity
        seen_voice.append(cfg)
        voice = ModelVoice()
        voice.model = cfg.voice["model"]
        return voice

    def style_for_config(cfg):
        from app.studio.application.render import style_from_effective_config
        seen_style.append(cfg)
        return style_from_effective_config(cfg)

    run, _, renderer = runner(w)
    run.effective_config_for = lambda video: calls.append(video) or config
    run.voice_for_config = voice_for_config
    run.style_for_config = style_for_config
    run.execute(job.id)
    spec = renderer.specs[0]

    # uma resolução por execução, e a MESMA configuração alimenta voz e plano
    assert len(calls) == 1 and calls[0].id == V
    assert seen_voice == [config] and seen_style == [config]
    assert spec.voice_id == "piper:pt_BR-jeff-medium"
    assert spec.style.snapshot.style_id == STYLE_ID and spec.style.snapshot.version == 1
    assert spec.style.motion == ("zoom_in", "pan_right") and spec.style.music == {"bpm": 90}
    assert spec.style.caption == {"font_size": 62} and spec.style.palette == {"accent": "#ff00aa"}
    # o plano carrega a identidade e a proveniência criativa do snapshot
    assert spec.config_snapshot.content_hash == config.content_hash
    assert spec.config_snapshot.schema_version == config.schema_version
    assert spec.config_snapshot.provenance["style"] == "video"
    assert "audiovisual.music.bpm" in spec.config_snapshot.provenance
    assert not any(key.startswith("editorial.") for key in spec.config_snapshot.provenance)


def test_changing_the_style_during_tts_does_not_change_the_render_in_progress(tmp_path):
    w = world(tmp_path)
    first = frozen_config(params={"music": {"bpm": 90}})
    second = frozen_config(params={"music": {"bpm": 140}})
    current = {"config": first}
    calls = []
    job = starter(w).execute(V)
    run, voice, renderer = runner(w)
    run.effective_config_for = lambda video: calls.append(video) or current["config"]

    def speak_during_a_style_change(text, out_path):
        current["config"] = second  # o estilo muda no meio do TTS
        voice.calls.append(text)
        Path(out_path).write_bytes(b"wav")
        return 2.0

    voice.speak = speak_during_a_style_change
    run.execute(job.id)
    spec = renderer.specs[0]  # com duas resoluções, este seria o estilo novo

    assert len(calls) == 1
    assert spec.style.music == {"bpm": 90}
    assert spec.config_snapshot.content_hash == first.content_hash


def test_a_retry_reads_the_run_snapshot_and_a_new_run_adopts_the_new_revision(tmp_path):
    from app.studio.domain.run_config import RunConfigStatus, StoredRunConfig

    w = world(tmp_path)
    old = frozen_config(params={"music": {"bpm": 90}})
    new = frozen_config(params={"music": {"bpm": 140}})
    run_id, new_run_id = "r" * 32, "n" * 32
    store = ConfigStore({run_id: StoredRunConfig(RunConfigStatus.RESOLVED, old)})

    def never_resolve(video):
        raise AssertionError("um run com snapshot não pode ser re-resolvido")

    job = starter(w).execute(V)
    run, _, renderer = runner(w)
    run.config_store = store
    run.effective_config_for = never_resolve
    run.execute(job.id, run_id=run_id)

    # retry: novo job, o MESMO run — snapshot lido de novo, nunca re-resolvido
    w["videos"].status = S.ASSETS_READY
    retry = starter(w).execute(V)
    run.execute(retry.id, run_id=run_id)

    # execução nova: outro run, que já nasceu com a revisão nova
    store.configs[new_run_id] = StoredRunConfig(RunConfigStatus.RESOLVED, new)
    w["videos"].status = S.ASSETS_READY
    fresh = starter(w).execute(V)
    run.execute(fresh.id, run_id=new_run_id)

    hashes = [spec.config_snapshot.content_hash for spec in renderer.specs]
    assert hashes == [old.content_hash, old.content_hash, new.content_hash]
    assert store.reads == [run_id, run_id, new_run_id]


def test_a_legacy_run_stays_legacy_and_is_never_re_resolved(tmp_path):
    from app.studio.domain.render_plan import StyleSnapshot
    from app.studio.domain.run_config import RunConfigStatus, StoredRunConfig
    from app.studio.domain.visual_style import ResolvedStyle

    w = world(tmp_path)
    legacy_style = ResolvedStyle(snapshot=StyleSnapshot(style_id="canal-1", version=3),
                                 music={"bpm": 90})
    store = ConfigStore({"l" * 32: StoredRunConfig(RunConfigStatus.LEGACY)})
    job = starter(w).execute(V)
    run, _, renderer = runner(w)
    run.config_store = store
    run.effective_config_for = lambda video: (_ for _ in ()).throw(
        AssertionError("run legado não ganha snapshot depois do fato"))
    run.style_for = lambda video: legacy_style
    run.execute(job.id, run_id="l" * 32)
    spec = renderer.specs[0]
    assert spec.style == legacy_style and spec.config_snapshot is None


def test_without_a_channel_profile_the_render_matches_the_legacy_path(tmp_path):
    """Sem canal/perfil, a configuração é o retrato legado: estilo neutro e voz do projeto."""
    w = world(tmp_path)
    empty = frozen_config(with_style=False)
    job = starter(w).execute(V)
    run, voice, renderer = runner(w)
    seen_voice, seen_style = [], []
    run.effective_config_for = lambda video: empty
    run.voice_for = lambda video: seen_voice.append(video) or voice
    run.style_for = lambda video: seen_style.append(video) or "não deveria ser lido"
    run.execute(job.id)
    configured = renderer.specs[0]

    legacy_world = world(tmp_path / "legacy")
    legacy_job = starter(legacy_world).execute(V)
    legacy_run, legacy_voice, legacy_renderer = runner(legacy_world)
    legacy_run.execute(legacy_job.id)
    legacy = legacy_renderer.specs[0]

    # a voz do projeto continua sendo a mesma (fallback legado), e o estilo é o neutro
    assert len(seen_voice) == 1 and seen_voice[0].id == V
    assert seen_style == [] and configured.style is None
    assert configured.voice_id == legacy.voice_id
    assert configured.music is legacy.music and configured.disclosure == legacy.disclosure
    assert configured.scene_seconds == legacy.scene_seconds
    assert [(c.start, c.end, c.text) for c in configured.cues] == \
        [(c.start, c.end, c.text) for c in legacy.cues]
    # o único acréscimo é a identidade da configuração no plano
    assert configured.config_snapshot is not None and legacy.config_snapshot is None
    assert configured.config_snapshot.provenance["style"] == "engine_default"


def test_availability_and_budget_are_still_dynamic_under_a_frozen_config(tmp_path):
    """O snapshot congela o criativo; assets e orçamento são checados em cada execução."""
    from app.studio.domain.run_config import RunConfigStatus, StoredRunConfig

    class Paid:
        def __init__(self):
            self.calls = []

        def run(self, key, video_id, amount, *, call, settle, allow_free_replay=False):
            self.calls.append(key)
            return call()

    w = world(tmp_path)
    config = frozen_config()
    run_id = "r" * 32
    store = ConfigStore({run_id: StoredRunConfig(RunConfigStatus.RESOLVED, config)})
    job = starter(w).execute(V)
    run, _, renderer = runner(w)
    run.config_store = store
    paid = Paid()
    run.paid = paid
    run.execute(job.id, run_id=run_id)
    assert len(paid.calls) == len(TEXTS)  # orçamento/comprovante por cena, por execução

    # disponibilidade do asset é relida: some depois do snapshot e o render recusa
    w["videos"].status = S.ASSETS_READY
    retry = starter(w).execute(V)
    w["scripts"].linked = False
    run.execute(retry.id, run_id=run_id)
    assert w["jobs"].jobs[retry.id].status == JobStatus.FAILED
    assert "asset" in w["jobs"].jobs[retry.id].error and len(renderer.specs) == 1


def test_the_style_projection_uses_only_the_declared_values_of_the_config():
    """A projeção não inventa valores: o que o motor decide continua decidido no motor."""
    from app.studio.application.render import style_from_effective_config

    declared = frozen_config(params={"music": {"bpm": 90}})
    style = style_from_effective_config(declared)
    assert style.music == {"bpm": 90}  # o seed default (7) não é materializado no plano
    assert style.motion == () and style.voice == {} and style.transition == {}
    assert style_from_effective_config(frozen_config(with_style=False)) is None


# ---------------------------------------------------------------------------
# P2-1 / P2-2 (REC-04.02): geometria segura de overlays/PiP e preservação de hash
# ---------------------------------------------------------------------------


def _rect_intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0


def _overlay_box_px(layer, width: int, height: int) -> tuple[int, int, int, int]:
    """Espelha exatamente a geometria de `_overlay_filter` em `render_plan_compiler.py`."""
    tw = max(16, int(width * layer.scale))
    th = max(16, int(height * layer.scale))
    x0 = int((width - tw) * layer.position_x)
    y0 = int((height - th) * layer.position_y)
    return (x0, y0, x0 + tw, y0 + th)


def test_overlay_layers_never_overlap_top_left_hud_or_bottom_caption_safe_zones(tmp_path):
    """P2-1: overlays/PiP (posições ímpares à direita e pares à esquerda) nunca sobrepõem
    a safe-zone do HUD/disclosure superior esquerdo (`x<=600, y<=260`) nem a faixa inferior de legendas.
    """
    from app.studio.domain.contracts import SceneAsset
    from app.studio.domain.render import SIZE

    w = world(tmp_path)
    scenes = w["scripts"].scenes(V)
    overlays = [
        SceneAsset(scene_id=scenes[0].id, asset_id="a" * 32, position=pos, start_s=0.5, end_s=2.5, role="overlay")
        for pos in (1, 2, 3, 4)
    ]
    w["scripts"].get_scene_assets = lambda sid: overlays if sid == scenes[0].id else []
    run, _, _ = runner(w)
    pairs = [(sc, w["assets"].get(sc.asset_id)) for sc in scenes]

    layers = run._overlay_layers(pairs, [5.0, 5.0, 5.0])
    assert len(layers) == 4

    # Safe-zone superior esquerda do static_overlay (disclosure y=96..135, selo FATO y=160..245 + margem)
    hud_safe_zone = (0, 0, 600, 260)
    caption_zones = {
        VideoFormat.long: (0, 880, 1920, 1080),
        VideoFormat.short: (0, 1500, 1080, 1920),
    }

    for fmt, (width, height) in SIZE.items():
        cap_zone = caption_zones[fmt]
        for layer in layers:
            box = _overlay_box_px(layer, width, height)
            assert not _rect_intersects(box, hud_safe_zone), (
                f"Overlay z={layer.z_index} ({layer.position_x}, {layer.position_y}) em {fmt.value} "
                f"box={box} colide com HUD/disclosure safe-zone {hud_safe_zone}"
            )
            assert not _rect_intersects(box, cap_zone), (
                f"Overlay z={layer.z_index} ({layer.position_x}, {layer.position_y}) em {fmt.value} "
                f"box={box} colide com faixa de legendas {cap_zone}"
            )


def test_overlay_layers_negative_cases_and_window_clamping(tmp_path):
    """P2-2: _overlay_layers recusa asset inexistente/sem licença e descarta janela end_s <= start_s."""
    from app.studio.domain.contracts import SceneAsset

    w = world(tmp_path)
    scenes = w["scripts"].scenes(V)
    pairs = [(sc, w["assets"].get(sc.asset_id)) for sc in scenes]
    run, _, _ = runner(w)

    # 1. Janela inválida (start_s >= length ou end_s <= start_s) é descartada sem erro
    w["scripts"].get_scene_assets = lambda sid: (
        [SceneAsset(scene_id=sid, asset_id="a" * 32, position=1, start_s=6.0, end_s=8.0, role="overlay")]
        if sid == scenes[0].id else []
    )
    assert run._overlay_layers(pairs, [5.0, 5.0, 5.0]) == ()

    # 2. Asset ausente -> RenderRefused (fail-closed)
    missing_id = "f" * 32
    orig_get = w["assets"].get
    w["assets"].get = lambda aid: None if aid == missing_id else orig_get(aid)
    w["scripts"].get_scene_assets = lambda sid: (
        [SceneAsset(scene_id=sid, asset_id=missing_id, position=1, start_s=0.5, end_s=2.0, role="overlay")]
        if sid == scenes[0].id else []
    )
    with pytest.raises(RenderRefused, match="not found"):
        run._overlay_layers(pairs, [5.0, 5.0, 5.0])

    # 3. Asset com licença em branco -> RenderRefused (fail-closed)
    unlicensed_id = "e" * 32
    w["assets"].get = lambda aid: (
        Asset.model_construct(id=aid, kind=AssetKind.image, cache_key=aid * 2, path=f"cache/ab/{aid}.png",
                              provider="import", model="m", license="   ")
        if aid == unlicensed_id else orig_get(aid)
    )
    w["scripts"].get_scene_assets = lambda sid: (
        [SceneAsset(scene_id=sid, asset_id=unlicensed_id, position=1, start_s=0.5, end_s=2.0, role="overlay")]
        if sid == scenes[0].id else []
    )
    with pytest.raises(RenderRefused, match="no license"):
        run._overlay_layers(pairs, [5.0, 5.0, 5.0])


def test_start_render_preserves_input_hash_without_overlays_and_invalidates_with_overlays(tmp_path):
    """P2-1/P2-2: vídeos sem overlays preservam o input_hash exato; anexar overlay altera o hash."""
    from app.studio.domain.contracts import SceneAsset

    w_base = world(tmp_path / "base")
    job_base = starter(w_base).execute(V)

    w_no_ov = world(tmp_path / "no_ov")
    w_no_ov["scripts"].get_scene_assets = lambda sid: []
    job_no_ov = starter(w_no_ov).execute(V)
    assert job_no_ov.input_hash == job_base.input_hash

    w_with_ov = world(tmp_path / "with_ov")
    first_scene_id = w_with_ov["scripts"].scenes(V)[0].id
    w_with_ov["scripts"].get_scene_assets = lambda sid: (
        [SceneAsset(scene_id=sid, asset_id="a" * 32, position=2, start_s=0.5, end_s=2.0, role="overlay")]
        if sid == first_scene_id else []
    )
    job_with_ov = starter(w_with_ov).execute(V)
    assert job_with_ov.input_hash != job_base.input_hash
