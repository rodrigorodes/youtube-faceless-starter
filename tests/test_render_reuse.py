"""RP-06b — reúso ponta a ponta: ``RunRender`` → executor (não só teste de unidade).

O aceite da RP-029 ("alterar uma cena não exige regenerar narrações, imagens ou vídeos de
outras cenas") hoje só valia no núcleo (grafo/cache, RP-06). Este teste prova que a decisão
é **consumida no caminho de produção**: com um runner FFmpeg de contagem (stub) injetado no
``PlanFfmpegRenderer`` real, mudar a cena A ⇒ **o FFmpeg roda para A + concat + final** e
**não roda para o vídeo da cena B**, cujo segmento vem do cache.

A prova é por **contagem de execuções do FFmpeg** (arquivos de saída dos comandos), não por
inspeção de bytes do MP4 — o runner stub grava o mesmo conteúdo em todo arquivo, então o que
importa é *quais* comandos rodaram.
"""
import math
import struct
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer  # noqa: E402
from app.studio.application.render import RunRender, StartRender  # noqa: E402
from app.studio.domain.contracts import (  # noqa: E402
    Asset, AssetKind, JobStatus, RenderJob, Scene, Video, VideoFormat, VideoStatus,
)
from app.studio.domain.qa_report import QaCoverage, QaReport  # noqa: E402
from app.studio.domain.render import SIZE, make_cues, scene_length  # noqa: E402
from app.studio.domain.render_cache import NodeId  # noqa: E402

S = VideoStatus
V, P = "v" * 32, "p" * 32
A, B = "a" * 32, "b" * 32
TEXTS = ["Primeira narração do vídeo de teste.", "Segunda narração, inalterada."]


class FakePlanRepository:
    """Mesma superfície do ``PostgresRenderPlanRepository``, em memória (sem banco)."""

    def __init__(self):
        self.documents: dict[tuple[str, int], object] = {}
        self._entries: dict[str, dict] = {}
        self.artifacts: dict[tuple[str, str], object] = {}

    def save_plan(self, plan):
        self.documents[(plan.plan_id, plan.revision)] = plan

    def get_plan(self, plan_id, revision):
        return self.documents.get((plan_id, revision))

    def latest_plan(self, plan_id):
        revisions = self.revisions(plan_id)
        return self.documents[(plan_id, revisions[-1])] if revisions else None

    def revisions(self, plan_id):
        return sorted(revision for (pid, revision) in self.documents if pid == plan_id)

    def record_entry(self, entry):
        self._entries.setdefault(entry.plan_id, {})[entry.node] = entry

    def record_entries(self, entries):
        for entry in entries:
            self.record_entry(entry)

    def entries(self, plan_id):
        return dict(self._entries.get(plan_id, {}))

    def record_artifacts(self, artifacts):
        for artifact in artifacts:
            self.artifacts[(artifact.content_sha256, artifact.location)] = artifact

    def artifact(self, content_sha256, location):
        return self.artifacts.get((content_sha256, location))


class StubRunner:
    """Conta e registra cada comando FFmpeg sem executá-lo; deixa o arquivo de saída."""

    def __init__(self):
        self.calls = []

    def __call__(self, cmd, timeout=600):
        self.calls.append((list(cmd), timeout))
        Path(cmd[-1]).write_bytes(b"stub")


def tone_wav(path, seconds=1.2, rate=22050):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(b"".join(struct.pack("<h", int(32767 * 0.4 * math.sin(2 * math.pi * 220 * i / rate))) for i in range(n)))


class Videos:
    def __init__(self):
        self.status = S.ASSETS_READY

    def get_video(self, video_id):
        return Video(id=V, project_id=P, topic="ADE 2026", format=VideoFormat.short, status=self.status)


class Scripts:
    def __init__(self, texts):
        self.texts = list(texts)

    def scenes(self, video_id):
        return [Scene(id=asset_id, video_id=V, idx=idx, narration=text, label="QUA", caption="x",
                      image_prompt="prompt de imagem válido", claim_ids=["c"], asset_id=asset_id)
                for idx, (asset_id, text) in enumerate(zip((A, B), self.texts))]


class Assets:
    def __init__(self):
        self.added = []

    def get(self, asset_id):
        return Asset(id=asset_id, kind=AssetKind.image, cache_key=asset_id * 2,
                     path=f"cache/ab/{asset_id}.png", provider="placeholder", model="g", license="CC0")

    def add(self, asset):
        self.added.append(asset)
        return asset


class Jobs:
    def __init__(self, videos):
        self.videos, self.jobs = videos, {}
        self.qa = None

    def enqueue(self, video_id, input_hash):
        for job in self.jobs.values():
            if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                return job, False
        job = RenderJob(id=f"{len(self.jobs) + 1:032x}", video_id=video_id, status=JobStatus.QUEUED,
                        attempt=len(self.jobs) + 1, input_hash=input_hash)
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
        return True

    def latest_output(self, video_id):
        return None

    def fail(self, job_id, error):
        self.jobs[job_id] = self.jobs[job_id].model_copy(update={"status": JobStatus.FAILED, "error": error})

    def complete(self, job_id, asset, qa):
        self.qa = qa
        self.jobs[job_id] = self.jobs[job_id].model_copy(update={"status": JobStatus.SUCCEEDED, "output_asset_id": asset.id})
        self.videos.status = S.AWAITING_APPROVAL if qa.is_publishable else S.RENDERED
        return True


class Files:
    def __init__(self, tmp):
        self.tmp = tmp

    def image_path(self, relative):
        return self.tmp / relative

    def work_dir(self, project_id, video_id, job_id):
        d = self.tmp / "work" / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def publish(self, project_id, video_id, job_id, mp4, srt):
        return f"projects/{project_id}/videos/{video_id}/final-{job_id}.mp4"

    def resolve(self, relative, kind):
        return self.tmp / relative

    def prune(self, project_id, video_id, keep):
        pass

    def cleanup(self, work_dir):
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)


class Voice:
    name = "tone"
    model = "ok"

    def __init__(self, seconds=1.2):
        self.seconds, self.calls = seconds, []

    def speak(self, text, out_path):
        self.calls.append(text)
        tone_wav(out_path, self.seconds)
        return self.seconds


class Quality:
    """Porta de QA falsa: devolve o relatório novo e publicável; mede a identidade entregue.

    A execução real do QA (ffprobe/ebur128) é provada em ``test_render_quality_e2e``; aqui
    o alvo é o reúso do executor, então o QA só precisa devolver a verdade persistível.
    """

    def __init__(self):
        self.calls = []

    def evaluate(self, plan, *, media_path, narration_path=None, descriptors=(), render_id, checksum):
        self.calls.append({"render_id": render_id, "checksum": checksum, "media": media_path})
        return QaReport(render_id=render_id, checksum=checksum, generated_at=datetime.now(timezone.utc),
                        coverage=QaCoverage(status="verified"), checks_run=("render.media_metrics",))


def world(tmp, texts=None):
    texts = list(texts or TEXTS)
    size = SIZE[VideoFormat.short]
    for idx, asset_id in enumerate((A, B)):
        img = tmp / "cache" / "ab" / f"{asset_id}.png"
        img.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (30 + 60 * idx, 80, 160 - 40 * idx)).save(img)
    videos = Videos()
    return {"videos": videos, "scripts": Scripts(texts), "assets": Assets(), "jobs": Jobs(videos),
            "files": Files(tmp), "voice": Voice()}


def starter(w):
    return StartRender(w["videos"], w["scripts"], w["assets"], w["jobs"], enqueue=lambda job_id: None)


def use_case(w, renderer, plans=None):
    return RunRender(w["videos"], w["scripts"], w["assets"], w["jobs"], w["files"],
                     voice_for=lambda project_id: w["voice"], renderer_for=lambda project_id: renderer,
                     quality=Quality(), plans=plans)


class SpecSpy:
    """Delega ao renderer real e guarda o ``RenderSpec`` de cada render (para inspecionar durações)."""

    name = "spy"

    def __init__(self, inner):
        self.inner, self.specs = inner, []

    def render(self, spec, out_path):
        self.specs.append(spec)
        return self.inner.render(spec, out_path)


class SkewedVoice(Voice):
    """Escreve um WAV de ``wav_seconds`` mas devolve ``seconds``: prova que o reúso mede o WAV real."""

    def __init__(self, seconds=1.2, wav_seconds=1.7):
        super().__init__(seconds)
        self.wav_seconds = wav_seconds

    def speak(self, text, out_path):
        self.calls.append(text)
        tone_wav(out_path, self.wav_seconds)
        return self.seconds


def outputs(runner):
    return [call[0][-1] for call in runner.calls]


def test_changing_one_scene_does_not_run_ffmpeg_for_the_other_scene(tmp_path):
    """O aceite da RP-029 no caminho de produção: A regenera; B vem do cache (sem FFmpeg)."""
    w = world(tmp_path)
    repo, runner = FakePlanRepository(), StubRunner()
    renderer = PlanFfmpegRenderer(runner=runner, plans=repo, cache_root=tmp_path / "cache")
    run = use_case(w, renderer)

    first_job = starter(w).execute(V)
    run.execute(first_job.id)
    assert len(runner.calls) == 4  # primeira revisão: A + B + concat + mixagem

    entries_before = repo.entries(f"plan:{V}")
    b_visual_before = entries_before[NodeId("visual", f"shot:{B}")].artifact_uri
    b_narration_before = entries_before[NodeId("narration", B)].artifact_uri
    a_visual_before = entries_before[NodeId("visual", f"shot:{A}")].artifact_uri

    # Muda SÓ a cena A; a cena B (narração e imagem) fica idêntica.
    w["scripts"].texts = ["Primeira narração totalmente reescrita.", TEXTS[1]]
    w["videos"].status = S.ASSETS_READY
    runner.calls.clear()
    second_job = starter(w).execute(V)
    run.execute(second_job.id)

    produced = outputs(runner)
    assert len(runner.calls) == 3, produced  # A + concat + final; o FFmpeg NÃO rodou para B
    assert str(tmp_path / "work" / second_job.id / "scene_000.mp4") in produced   # cena A: re-renderizada
    assert str(tmp_path / "work" / second_job.id / "scene_001.mp4") not in produced  # cena B: do cache
    assert produced[-1] == str(tmp_path / "work" / second_job.id / "final.mp4")   # composição final recomposta

    entries_after = repo.entries(f"plan:{V}")
    assert entries_after[NodeId("visual", f"shot:{B}")].artifact_uri == b_visual_before
    assert entries_after[NodeId("narration", B)].artifact_uri == b_narration_before
    assert entries_after[NodeId("visual", f"shot:{A}")].artifact_uri != a_visual_before


def test_render_is_registered_so_the_next_cycle_has_a_cache_hit(tmp_path):
    """Sem ciclo de registro não há hit: o primeiro render grava o índice do segundo."""
    w = world(tmp_path)
    repo, runner = FakePlanRepository(), StubRunner()
    run = use_case(w, PlanFfmpegRenderer(runner=runner, plans=repo, cache_root=tmp_path / "cache"))

    run.execute(starter(w).execute(V).id)
    assert repo.revisions(f"plan:{V}") == [1]
    entries = repo.entries(f"plan:{V}")
    assert {NodeId("visual", f"shot:{A}"), NodeId("visual", f"shot:{B}"),
            NodeId("narration", A), NodeId("narration", B),
            NodeId("concat", "video"), NodeId("final", "video")} <= set(entries)
    for entry in entries.values():
        assert len(entry.artifact_sha256) == 64 and Path(entry.artifact_uri).is_file()

    # Segundo render idêntico: nada roda (nem instância de QaReport muda de contrato).
    w["videos"].status = S.ASSETS_READY
    runner.calls.clear()
    run.execute(starter(w).execute(V).id)
    assert runner.calls == [] and repo.revisions(f"plan:{V}") == [1, 2]


# ------------------------------- RP-06c: o TTS deixa de rodar para a cena intacta -------------------------------
#
# A RP-06b provou o reúso do **vídeo** de B por contagem de FFmpeg, mas o `Voice.speak` ainda era
# chamado para **toda** cena: o fingerprint da narração incluía a duração da fala — saída do TTS.
# Aqui o fingerprint é da **entrada** (texto + voz) e o `RunRender` consulta o cache antes de
# sintetizar: a narração em cache (WAV íntegro) é reusada e o `speak` NÃO é chamado para a cena B.


def test_changing_one_scene_does_not_speak_for_the_other_scene(tmp_path):
    """O aceite literal da RP-029 para narração no caminho de produção (RunRender → executor)."""
    w = world(tmp_path)
    repo, runner = FakePlanRepository(), StubRunner()
    renderer = PlanFfmpegRenderer(runner=runner, plans=repo, cache_root=tmp_path / "cache")
    run = use_case(w, renderer, plans=repo)

    run.execute(starter(w).execute(V).id)
    assert w["voice"].calls == list(TEXTS)  # 1ª revisão: sintetiza as duas cenas

    # Muda SÓ a cena A; a narração de B fica idêntica.
    w["scripts"].texts = ["Primeira narração totalmente reescrita.", TEXTS[1]]
    w["videos"].status = S.ASSETS_READY
    w["voice"].calls.clear()
    run.execute(starter(w).execute(V).id)

    assert w["voice"].calls == ["Primeira narração totalmente reescrita."]  # só A sintetiza; B veio do cache
    assert TEXTS[1] not in w["voice"].calls


def test_a_corrupted_cached_narration_is_not_reused(tmp_path):
    """Honestidade do cache: WAV de narração com hash divergente não é reusado — volta a sintetizar."""
    w = world(tmp_path)
    repo, runner = FakePlanRepository(), StubRunner()
    renderer = PlanFfmpegRenderer(runner=runner, plans=repo, cache_root=tmp_path / "cache")
    run = use_case(w, renderer, plans=repo)

    run.execute(starter(w).execute(V).id)
    b_wav = repo.entries(f"plan:{V}")[NodeId("narration", B)].artifact_uri
    Path(b_wav).write_bytes(b"corrompido")  # o conteúdo deixa de bater com o hash registrado

    w["scripts"].texts = ["Primeira narração reescrita por completo.", TEXTS[1]]  # A muda, B não
    w["videos"].status = S.ASSETS_READY
    w["voice"].calls.clear()
    run.execute(starter(w).execute(V).id)

    # sem a corrupção B seria reusado; com o hash divergente, B volta a sintetizar
    assert "Primeira narração reescrita por completo." in w["voice"].calls
    assert TEXTS[1] in w["voice"].calls


def test_a_reused_narration_takes_the_real_duration_from_the_reused_wav(tmp_path):
    """A duração de uma cena reusada é a **real** do WAV (medida), não o retorno do TTS nem estimativa."""
    w = world(tmp_path)
    w["voice"] = SkewedVoice(seconds=1.2, wav_seconds=1.7)  # o WAV é mais longo que o retorno
    repo, runner = FakePlanRepository(), StubRunner()
    spy = SpecSpy(PlanFfmpegRenderer(runner=runner, plans=repo, cache_root=tmp_path / "cache"))
    run = use_case(w, spy, plans=repo)

    run.execute(starter(w).execute(V).id)
    assert spy.specs[0].scene_seconds == [scene_length(1.2), scene_length(1.2)]  # 1º render usa o retorno do TTS

    w["videos"].status = S.ASSETS_READY
    w["voice"].calls.clear()
    run.execute(starter(w).execute(V).id)

    assert w["voice"].calls == []  # nada de TTS: as duas narrações vieram do cache
    assert spy.specs[1].scene_seconds == [scene_length(1.7), scene_length(1.7)]  # duração REAL do WAV reusado

