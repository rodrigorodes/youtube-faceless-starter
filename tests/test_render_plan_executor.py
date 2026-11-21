"""RP-024..RP-026 — executor FFmpeg do Render Plan (o único caminho de render).

O executor consome o ``CompiledRender`` do compilador puro e materializa o vídeo:
overlays (selo/disclosure/legendas/card de texto) com Pillow, trilha sintetizada,
narração montada, um ``ffmpeg`` por shot, concat sem reencode, mixagem com ducking +
``loudnorm`` e **publicação atômica** (temp + ``os.replace``).

Aqui os comandos são validados por unidade (``runner`` injetado, sem FFmpeg) e a
paridade com o renderer removido é medida por ``evaluate_qa`` (duração ±1 s, resolução,
LUFS, silêncio/preto) em clipes curtos — não por hash byte-a-byte nem SSIM.
"""
import math
import shutil
import struct
import sys
import wave
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.qa_ffmpeg import FfmpegQa  # noqa: E402
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer  # noqa: E402
from app.studio.application.config import build  # noqa: E402
from app.studio.application.ports import RenderSpec  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.contracts import Scene, VideoFormat  # noqa: E402
from app.studio.domain.render import SIZE, evaluate_qa, make_cues, scene_length  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

SCENE_A = "a" * 32
SCENE_B = "b" * 32
VIDEO = "v" * 32


def tone_wav(path, seconds=1.0, amplitude=0.4, rate=22050):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(b"".join(struct.pack("<h", int(32767 * amplitude * math.sin(2 * math.pi * 220 * i / rate))) for i in range(n)))


def spec_for(tmp, fmt=VideoFormat.short, scene_seconds=(2.0,), amplitude=0.4, music=True, texts=None):
    size = SIZE[fmt]
    texts = texts or tuple(f"Narração da cena {i} para o teste automatizado do executor." for i in range(len(scene_seconds)))
    scenes, images, wavs, lengths, cues, offset = [], [], [], [], [], 0.0
    for i, seconds in enumerate(scene_seconds):
        cid = (SCENE_A, SCENE_B)[i] if i < 2 else f"{i:032x}"
        img = tmp / f"img{i}.png"
        Image.new("RGB", size, (30 + 60 * i, 80, 160 - 40 * i)).save(img)
        wav = tmp / f"s{i}.wav"
        tone_wav(wav, seconds, amplitude)
        length = scene_length(seconds)
        scenes.append(Scene(id=cid, video_id=VIDEO, idx=i, narration=texts[i], label="QUA",
                            caption="x", image_prompt="prompt de imagem válido", claim_ids=["c"], asset_id=cid))
        images.append(img), wavs.append(wav), lengths.append(length)
        cues += make_cues(texts[i], offset, seconds)
        offset += length
    work = tmp / "work"
    work.mkdir(exist_ok=True)
    return RenderSpec(scenes=scenes, images=images, speech_wavs=wavs, scene_seconds=lengths, cues=cues,
                      format=fmt, music=music, work_dir=work)


class StubRunner:
    """Registra os comandos sem executar FFmpeg; cada comando deixa o seu arquivo de saída."""

    def __init__(self):
        self.calls = []

    def __call__(self, cmd, timeout=600):
        self.calls.append((list(cmd), timeout))
        Path(cmd[-1]).write_bytes(b"stub")


# ------------------------------------------------------------------ grafo / comando (sem FFmpeg)


def test_executor_materializes_overlays_writes_audio_and_runs_the_planned_commands(tmp_path):
    spec = spec_for(tmp_path)
    runner = StubRunner()
    out = PlanFfmpegRenderer(runner=runner).render(spec, tmp_path / "work" / "final.mp4")
    assert out == tmp_path / "work" / "final.mp4" and out.read_bytes() == b"stub"
    assert (tmp_path / "work" / "static_000.png").exists()           # selo + disclosure
    assert list((tmp_path / "work").glob("cue_000_*.png"))           # legenda queimada por trecho
    assert (tmp_path / "work" / "narration.wav").exists()
    assert (tmp_path / "work" / "music.wav").exists()
    # um ffmpeg por shot, depois concat e por fim a mixagem — nunca um .tmp deixado para trás
    assert len(runner.calls) == len(spec.scenes) + 2
    assert runner.calls[-2][0][:3] == ["ffmpeg", "-hide_banner", "-loglevel"] and "concat" in runner.calls[-2][0]
    assert runner.calls[-1][0][-1] == str(tmp_path / "work" / "final.mp4")
    assert not list((tmp_path / "work").glob("*.tmp"))


def test_executor_publishes_atomically_and_leaves_no_partial_file(tmp_path):
    spec = spec_for(tmp_path)
    runner = StubRunner()
    out = tmp_path / "published" / "final.mp4"
    PlanFfmpegRenderer(runner=runner).render(spec, out)
    assert out.exists() and out.read_bytes() == b"stub"
    assert not list(out.parent.glob("*.tmp"))  # só o arquivo final aparece no destino


def test_ken_burns_motion_is_declared_in_the_plan_not_a_render_time_modulo(tmp_path):
    # o efeito visual do renderer removido é preservado, mas o plano carrega o movimento
    # explícito por cena (Effects.motion); o compilador não aplica `index % 4`
    spec = spec_for(tmp_path, scene_seconds=(2.0, 1.5), texts=("Primeira narração do vídeo de teste.", "Segunda narração, menor."))
    compiled = PlanFfmpegRenderer().compile_spec(spec)
    assert "zoompan=z='1+0.10*on/" in compiled.shots[0].filter_complex   # cena 0: zoom_in (declarado)
    assert "zoompan=z='1.10-0.10*on/" in compiled.shots[1].filter_complex  # cena 1: zoom_out (declarado)
    overridden = PlanFfmpegRenderer(motions={SCENE_A: "pan_right"}).compile_spec(spec)
    assert "zoompan=z='1.12':x='(iw-iw/zoom)*on/" in overridden.shots[0].filter_complex
    static = PlanFfmpegRenderer(cycle=()).compile_spec(spec)
    assert "zoompan=z='1':x='iw/2-(iw/zoom/2)'" in static.shots[0].filter_complex


def test_compiled_caption_windows_are_semi_open(tmp_path):
    compiled = PlanFfmpegRenderer().compile_spec(spec_for(tmp_path))
    enables = [c.enable for shot in compiled.shots for c in shot.captions]
    assert enables and all(e.startswith("gte(t,") and "*lt(t," in e for e in enables)


def test_executor_writes_a_silent_music_track_when_music_is_off(tmp_path):
    spec = spec_for(tmp_path, music=False)
    PlanFfmpegRenderer(runner=StubRunner()).render(spec, tmp_path / "work" / "final.mp4")
    with wave.open(str(tmp_path / "work" / "music.wav"), "rb") as w:
        frames = w.readframes(w.getnframes())
        assert w.getframerate() == 44100 and w.getnframes() > 0
        assert frames == b"\x00" * len(frames)  # trilha muda de mesmo comprimento (C2)


def test_two_scenes_sharing_one_asset_compile_once_in_the_manifest(tmp_path):
    import dataclasses

    spec = spec_for(tmp_path, scene_seconds=(2.0, 1.5), texts=("Primeira narração do vídeo de teste.", "Segunda narração, menor."))
    scenes = [scene.model_copy(update={"asset_id": SCENE_A}) for scene in spec.scenes]
    shared = dataclasses.replace(spec, scenes=scenes, images=[spec.images[0], spec.images[0]])
    compiled = PlanFfmpegRenderer().compile_spec(shared)
    assert [shot.asset_id for shot in compiled.shots] == [SCENE_A, SCENE_A]


def test_multi_scene_plan_uses_one_segment_per_scene_in_order(tmp_path):
    spec = spec_for(tmp_path, scene_seconds=(2.0, 1.5), texts=("Primeira narração do vídeo de teste.", "Segunda narração, menor."))
    compiled = PlanFfmpegRenderer().compile_spec(spec)
    assert [s.scene_id for s in compiled.shots] == [SCENE_A, SCENE_B]
    for previous, current in zip(compiled.shots, compiled.shots[1:]):
        assert previous.start_ticks + previous.duration_ticks == current.start_ticks


def test_spec_without_a_linked_asset_is_refused_with_a_clear_error(tmp_path):
    import dataclasses

    spec = spec_for(tmp_path)
    broken = dataclasses.replace(spec, scenes=[spec.scenes[0].model_copy(update={"asset_id": None})])
    with pytest.raises(RuntimeError, match="asset"):
        PlanFfmpegRenderer().compile_spec(broken)


def test_unreadable_image_is_refused_with_a_clear_error(tmp_path):
    spec = spec_for(tmp_path)
    spec.images[0].write_bytes(b"nao e imagem")
    with pytest.raises(RuntimeError, match="image"):
        PlanFfmpegRenderer().compile_spec(spec)


def test_the_registered_ffmpeg_renderer_is_the_plan_renderer():
    Studio(Settings())  # registra os provedores (sem banco)
    renderer = build("renderer", "ffmpeg:rich")
    assert isinstance(renderer, PlanFfmpegRenderer)
    # RP-06b: a composição é o único lugar que injeta o repositório do plano e a raiz do cache
    # no executor. Sem esta fiação, o reúso não roda no caminho de produção.
    assert renderer.plans is not None and renderer.cache_root is not None


def test_the_kill_switch_still_disables_the_plan_renderer():
    from app.studio.adapters.render_disabled import DisabledRenderer

    Studio(Settings(render_plan_enabled=False))
    assert isinstance(build("renderer", "ffmpeg:rich"), DisabledRenderer)


# ------------------------------------------------------------------ paridade medida (FFmpeg)


@pytest.mark.parametrize("fmt", [VideoFormat.short, VideoFormat.long])
@needs_ffmpeg
def test_plan_path_renders_the_expected_resolution_and_passes_qa(tmp_path, fmt):
    spec = spec_for(tmp_path, fmt)
    out = PlanFfmpegRenderer().render(spec, tmp_path / "work" / "final.mp4")
    metrics = FfmpegQa().analyze(out, narration=spec.work_dir / "narration.wav")
    qa = evaluate_qa({**metrics, "expected_s": round(sum(spec.scene_seconds), 3)}, fmt)
    assert qa.passed, qa.failures
    assert (metrics["width"], metrics["height"]) == SIZE[fmt]
    assert metrics["duration_s"] == pytest.approx(sum(spec.scene_seconds), abs=1.0)
    assert -45 < metrics["integrated_lufs"] < -9
    assert metrics["silence_ratio"] < 0.6 and metrics["black_ratio"] < 0.3


@needs_ffmpeg
def test_multi_scene_plan_renders_and_stays_within_the_qa_envelope(tmp_path):
    spec = spec_for(tmp_path, scene_seconds=(2.0, 1.5), texts=("Primeira narração do vídeo de teste.", "Segunda narração, menor."))
    out = PlanFfmpegRenderer().render(spec, tmp_path / "work" / "final.mp4")
    metrics = FfmpegQa().analyze(out, narration=spec.work_dir / "narration.wav")
    qa = evaluate_qa({**metrics, "expected_s": round(sum(spec.scene_seconds), 3)}, spec.format)
    assert qa.passed, qa.failures
    assert metrics["narration_lufs"] is not None and metrics["narration_lufs"] > -45


# ------------------------- RP-06b: reúso consumido pelo executor (sem FFmpeg) -------------------------
#
# O grafo e o índice de cache **decidem** o reúso (RP-06); aqui o executor **consome** a decisão:
# um shot/narração/montagem em ``cache_hits`` não roda FFmpeg — o artefato físico é copiado.
# A prova é por **contagem de execuções** do runner (stub), não por inspeção do MP4.


class FakePlanRepository:
    """Superfície do repositório versionado, em memória, sem banco (mesma do Postgres)."""

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


def _outputs(runner):
    return [call[0][-1] for call in runner.calls]


def test_changing_one_scene_reuses_the_other_scene_without_running_ffmpeg(tmp_path):
    """Mudar A ⇒ o FFmpeg roda para A + concat + final; o segmento de B vem do cache."""
    first = spec_for(tmp_path, scene_seconds=(2.0, 1.5), texts=("Primeira cena.", "Segunda cena."))
    repo, runner = FakePlanRepository(), StubRunner()
    renderer = PlanFfmpegRenderer(runner=runner, plans=repo, cache_root=tmp_path / "cache")

    renderer.render(first, first.work_dir / "final.mp4")
    assert len(runner.calls) == 4  # primeira revisão: 2 shots + concat + mixagem

    changed = spec_for(tmp_path, scene_seconds=(2.0, 1.5),
                       texts=("Primeira cena reescrita por completo.", "Segunda cena."))
    runner.calls.clear()
    renderer.render(changed, changed.work_dir / "final.mp4")

    outputs = _outputs(runner)
    assert len(runner.calls) == 3, outputs  # A + concat + final (B reusado)
    assert str(tmp_path / "work" / "scene_000.mp4") in outputs
    assert str(tmp_path / "work" / "scene_001.mp4") not in outputs  # o FFmpeg não rodou para B
    assert str(tmp_path / "work" / "video_only.mp4") in outputs and str(tmp_path / "work" / "final.mp4") in outputs


def test_rendering_the_same_plan_again_reuses_the_final_mp4_without_ffmpeg(tmp_path):
    """Nada mudou ⇒ acerto total: o MP4 final é o próprio artefato físico, zero FFmpeg."""
    spec = spec_for(tmp_path, scene_seconds=(2.0,), texts=("Cena única do teste de reúso.",))
    repo, runner = FakePlanRepository(), StubRunner()
    renderer = PlanFfmpegRenderer(runner=runner, plans=repo, cache_root=tmp_path / "cache")

    renderer.render(spec, spec.work_dir / "final.mp4")
    assert len(runner.calls) == 3  # 1 shot + concat + mixagem
    runner.calls.clear()
    out = renderer.render(spec, spec.work_dir / "final.mp4")

    assert runner.calls == []  # nem um ffmpeg: o final saiu do cache
    assert out.read_bytes() == b"stub"


def test_a_corrupted_cached_artifact_is_not_reused(tmp_path):
    """Honestidade do cache: artefato com hash divergente não é reusado — re-renderiza."""
    spec = spec_for(tmp_path, scene_seconds=(2.0,), texts=("Cena do teste de corrupção.",))
    repo, runner = FakePlanRepository(), StubRunner()
    renderer = PlanFfmpegRenderer(runner=runner, plans=repo, cache_root=tmp_path / "cache")
    renderer.render(spec, spec.work_dir / "final.mp4")

    for entry in repo.entries(f"plan:{spec.scenes[0].video_id}").values():
        Path(entry.artifact_uri).write_bytes(b"corrompido")  # o conteúdo deixa de bater com o hash
    runner.calls.clear()
    renderer.render(spec, spec.work_dir / "final.mp4")

    # nenhum artefato confere: tudo é regenerado (o "final" inclusive)
    assert len(runner.calls) == 3 and str(tmp_path / "work" / "scene_000.mp4") in _outputs(runner)
