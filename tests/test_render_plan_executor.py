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
from app.studio.domain.render_cache import NodeId  # noqa: E402

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


def test_materialized_overlays_are_transparent_and_keep_the_shorts_ui_area_free(tmp_path):
    # Portado de tests/test_rich.py (make_overlay): a produção dos overlays saiu do rich.py
    # para o executor do plano — static_overlay (selo/disclosure) e caption_overlay (legenda).
    from app.studio.adapters.render_plan_ffmpeg import caption_overlay, static_overlay

    width, height = SIZE[VideoFormat.short]
    static = tmp_path / "static.png"
    static_overlay(VideoFormat.short, "QUA • 21/10", "Ilustração gerada por IA", static)
    static_img = Image.open(static)
    assert static_img.size == (width, height) and static_img.mode == "RGBA"
    assert static_img.getchannel("A").getextrema()[0] == 0  # transparente onde não há conteúdo

    caption = tmp_path / "caption.png"
    caption_overlay(VideoFormat.short, "Legenda de teste bem longa " * 4, caption)
    caption_img = Image.open(caption)
    assert caption_img.size == (width, height) and caption_img.mode == "RGBA"
    alpha = caption_img.getchannel("A")
    assert alpha.getextrema()[0] == 0 and alpha.getextrema()[1] > 150  # texto opaco presente
    assert alpha.crop((0, 1700, width, height)).getextrema() == (0, 0)  # área inferior da UI dos Shorts fica livre


# ------------------------- VS-04: legenda/cores vêm do estilo (puro + executor) -------------------------


def _resolved(**params):
    import dataclasses

    from app.studio.domain.render_plan import StyleSnapshot
    from app.studio.domain.visual_style import ResolvedStyle

    return ResolvedStyle(snapshot=StyleSnapshot(style_id="canal-7", version=3), **params)


def test_caption_layout_without_a_style_is_the_current_default_and_the_style_overrides_it():
    from app.studio.adapters.render_plan_ffmpeg import _LAYOUT, caption_layout

    assert caption_layout(VideoFormat.short) == _LAYOUT[VideoFormat.short]
    assert caption_layout(VideoFormat.long, None) == _LAYOUT[VideoFormat.long]
    lay = caption_layout(VideoFormat.short, _resolved(caption={"font_size": 40, "bottom": 1400}))
    assert lay["caption_font"] == 40 and lay["caption_bottom"] == 1400
    # o estilo sobrepõe só o que declara: o resto do layout continua o default
    assert lay["caption_side"] == _LAYOUT[VideoFormat.short]["caption_side"]
    assert lay["box_side"] == _LAYOUT[VideoFormat.short]["box_side"] and lay["line_h"] == _LAYOUT[VideoFormat.short]["line_h"]


def test_overlay_colors_without_a_style_are_the_current_defaults_and_the_palette_overrides_them():
    from app.studio.adapters.render_plan_ffmpeg import overlay_colors

    current = {"caption_text": (255, 255, 255, 255), "caption_box": (0, 0, 0, 165), "accent": (255, 0, 140, 235)}
    assert overlay_colors() == current
    assert overlay_colors(_resolved()) == current  # estilo sem palette: default idêntico
    colors = overlay_colors(_resolved(palette={"caption_text": "#112233", "caption_box": "#00FF00", "accent": "#ABCDEF80"}))
    assert colors == {"caption_text": (0x11, 0x22, 0x33, 255), "caption_box": (0, 255, 0, 255), "accent": (0xAB, 0xCD, 0xEF, 0x80)}


def test_the_style_actually_changes_the_burned_caption_overlay(tmp_path):
    from app.studio.adapters.render_plan_ffmpeg import caption_layout, caption_overlay

    text = "Legenda do estilo visual aplicado pelo produtor."
    plain, styled = tmp_path / "plain.png", tmp_path / "styled.png"
    style = _resolved(caption={"font_size": 44, "bottom": 1300}, palette={"caption_box": "#00FF00"})
    caption_overlay(VideoFormat.short, text, plain)
    caption_overlay(VideoFormat.short, text, styled, style=style)

    assert plain.read_bytes() != styled.read_bytes()  # o estilo mudou o overlay de verdade
    # caixa default: preta translúcida na posição default (x < caption_side: só a caixa, sem texto;
    # y longe do canto arredondado de radius=36)
    assert Image.open(plain).getpixel((75, 1500)) == (0, 0, 0, 165)
    # caixa do estilo: verde opaca, subida para o bottom do estilo
    bottom = caption_layout(VideoFormat.short, style)["caption_bottom"]
    assert Image.open(styled).getpixel((75, bottom - 50)) == (0, 255, 0, 255)


def test_a_style_without_caption_or_palette_keeps_the_overlay_byte_for_byte(tmp_path):
    from app.studio.adapters.render_plan_ffmpeg import static_overlay, caption_overlay

    text = "Legenda que não muda sem parâmetros de estilo."
    plain, empty = tmp_path / "plain.png", tmp_path / "empty.png"
    caption_overlay(VideoFormat.short, text, plain)
    caption_overlay(VideoFormat.short, text, empty, style=_resolved())  # caption/palette vazios
    assert plain.read_bytes() == empty.read_bytes()

    badge_plain, badge_empty = tmp_path / "b_plain.png", tmp_path / "b_empty.png"
    static_overlay(VideoFormat.short, "QUA • 21/10", "Ilustração gerada por IA", badge_plain)
    static_overlay(VideoFormat.short, "QUA • 21/10", "Ilustração gerada por IA", badge_empty, style=_resolved())
    assert badge_plain.read_bytes() == badge_empty.read_bytes()


def test_executor_burns_the_caption_box_with_the_resolved_style(tmp_path):
    # Prova pelo caminho de produção: o ``render`` leva ``spec.style`` até a materialização
    # e a legenda queimada sai com a cor/posição do estilo (não com o default hardcoded).
    import dataclasses

    spec = spec_for(tmp_path, texts=("Narração da cena com estilo aplicado no overlay.",))
    styled = dataclasses.replace(spec, style=_resolved(caption={"bottom": 1300}, palette={"caption_box": "#00FF00"}))
    PlanFfmpegRenderer(runner=StubRunner()).render(styled, tmp_path / "work" / "final.mp4")
    cue = next((tmp_path / "work").glob("cue_000_*.png"))
    assert Image.open(cue).getpixel((75, 1250)) == (0, 255, 0, 255)  # caixa verde do estilo, no bottom do estilo


def test_executor_without_a_style_burns_the_default_caption_box(tmp_path):
    spec = spec_for(tmp_path, texts=("Narração da cena sem estilo no overlay.",))
    PlanFfmpegRenderer(runner=StubRunner()).render(spec, tmp_path / "work" / "final.mp4")
    cue = next((tmp_path / "work").glob("cue_000_*.png"))
    assert Image.open(cue).getpixel((75, 1500)) == (0, 0, 0, 165)  # caixa preta translúcida de sempre


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


def test_plan_style_snapshot_comes_from_the_spec_and_falls_back_when_absent(tmp_path):
    # RP-016/VS-03: com um canal/estilo resolvido a montante, o plano aponta para ele; sem
    # canal, o bundle neutro ``studio-default@1`` é usado (não há identidade real a referenciar).
    import dataclasses

    from app.studio.domain.render_plan import StyleSnapshot
    from app.studio.domain.visual_style import ResolvedStyle
    spec = spec_for(tmp_path)
    assert PlanFfmpegRenderer()._build_plan(spec).style_snapshot == StyleSnapshot(style_id="studio-default", version=1)
    channel = ResolvedStyle(snapshot=StyleSnapshot(style_id="canal-7", version=3))
    plan = PlanFfmpegRenderer()._build_plan(dataclasses.replace(spec, style=channel))
    assert plan.style_snapshot == channel.snapshot


def test_plan_applies_the_style_motion_cycle_and_music_params(tmp_path):
    # VS-03: o motion do estilo sobrepõe o ciclo default da instância e a música passa a usar
    # os params do estilo (bpm/seed) em vez do default hardcoded.
    import dataclasses

    from app.studio.domain.render_plan import StyleSnapshot
    from app.studio.domain.visual_style import ResolvedStyle
    spec = spec_for(tmp_path, scene_seconds=(2.0, 1.5),
                    texts=("Primeira narração do vídeo de teste.", "Segunda narração, menor."))
    style = ResolvedStyle(snapshot=StyleSnapshot(style_id="canal-7", version=3),
                          motion=("pan_left",), music={"bpm": 90, "seed": 4})
    plan = PlanFfmpegRenderer()._build_plan(dataclasses.replace(spec, style=style))
    motions = [shot.effects.motion for scene in plan.timeline.scenes for shot in scene.shots]
    assert motions == ["pan_left", "pan_left"]  # ciclo do estilo, não o KEN_BURNS_CYCLE default
    music = next(a for a in plan.generated_audio if a.kind == "music")
    assert music.params == {"bpm": 90, "seed": 4}


def test_plan_without_a_style_keeps_the_default_motion_cycle_and_music(tmp_path):
    spec = spec_for(tmp_path, scene_seconds=(2.0, 1.5),
                    texts=("Primeira narração do vídeo de teste.", "Segunda narração, menor."))
    plan = PlanFfmpegRenderer()._build_plan(spec)
    motions = [shot.effects.motion for scene in plan.timeline.scenes for shot in scene.shots]
    assert motions == ["zoom_in", "zoom_out"]  # KEN_BURNS_CYCLE por posição
    music = next(a for a in plan.generated_audio if a.kind == "music")
    assert music.params == {"bpm": 122, "seed": 7}  # DEFAULT_MUSIC_PARAMS


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


# ------------------------------------------- VE-02: o executor desenha o overlay compilado


def _compiled_with_overlay(work_dir):
    from app.studio.application.render_compiler import compile_render_plan
    from app.studio.domain.asset_resolver import AssetDescriptor
    from app.studio.domain.contracts import Asset, AssetKind
    from app.studio.domain.render_plan import StyleSnapshot
    from app.studio.domain.render_plan_builder import (
        StoryboardOverlay,
        StoryboardScene,
        asset_reference_for,
        build_render_plan,
    )

    def reference(asset_id, sha):
        return asset_reference_for(
            Asset(id=asset_id, kind=AssetKind.image, cache_key=sha, path=f"img/{asset_id}.png",
                  provider="p", model="m", license="CC0"),
            content_sha256=sha, media_type="image")

    def descriptor(asset_id, sha):
        return AssetDescriptor(asset_id=asset_id, asset_version=1, uri=f"img/{asset_id}.png",
                               content_sha256=sha, media_type="image", license="CC0",
                               available=True, codec="png", width=1080, height=1920)

    plan = build_render_plan(
        plan_id="plan:overlay", revision=1, project_id="p", video_id="v", format=VideoFormat.short,
        scenes=[StoryboardScene(scene_id="scene-01", asset_id="base", narration="Narração de teste.",
                                speech_seconds=2.0)],
        assets=[reference("base", "a" * 64), reference("overlay", "b" * 64)],
        style_snapshot=StyleSnapshot(style_id="s", version=1),
        overlays=[StoryboardOverlay(scene_id="scene-01", asset_id="overlay", start_s=0.1, duration_s=0.5)],
    )
    return compile_render_plan(plan=plan, assets={"base": descriptor("base", "a" * 64),
                                                  "overlay": descriptor("overlay", "b" * 64)},
                               work_dir=str(work_dir))


def test_execute_draws_a_compiled_plan_with_overlay_instead_of_refusing(tmp_path):
    """VE-02: o overlay compilado é desenhado no segmento base — não há mais recusa.

    A prova por unidade é o comando do segmento: a imagem do overlay entra como
    ``-loop 1 -i`` e o ``overlay`` fica habilitado só na janela relativa ao segmento base.
    """
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    compiled = _compiled_with_overlay(work)
    assert compiled.shots[0].overlays
    wav = tmp_path / "s.wav"
    tone_wav(wav)
    runner = StubRunner()
    out = PlanFfmpegRenderer(runner=runner).execute(compiled, [wav], tmp_path / "final.mp4")
    assert out.exists() and out.read_bytes() == b"stub"
    shot = compiled.shots[0]
    # a imagem do overlay entra como entrada extra, repetida, e o filtro só vale na janela
    assert shot.args[shot.args.index("-loop") + 1] == "1"
    assert "force_original_aspect_ratio" in shot.filter_complex
    assert "enable='gte(t,0.100)*lt(t,0.600)'" in shot.filter_complex
    assert len(runner.calls) == len(compiled.shots) + 2  # segmento + concat + mixagem


# ------------------- W3.2: presets alimentam o executor; grupos não aplicados não mexem -------------------


def test_a_preset_feeds_the_executor_caption_and_palette():
    # O preset é uma partida honesta: os grupos aplicáveis (caption/palette/motion/music) chegam
    # ao executor e mudam a legenda/cores de verdade — sem inventar dialeto paralelo.
    from app.studio.adapters.render_plan_ffmpeg import caption_layout, overlay_colors
    from app.studio.domain.visual_style import preset_params

    params = preset_params("documentario")
    style = _resolved(caption=params["caption"], palette=params["palette"],
                      motion=tuple(params["motion"]), music=params["music"])
    lay = caption_layout(VideoFormat.short, style)
    assert lay["caption_font"] == 52 and lay["caption_bottom"] == 1520
    colors = overlay_colors(style)
    assert colors["accent"] == (0xD4, 0xAF, 0x37, 255)
    assert colors["caption_text"] == (0xF2, 0xF2, 0xF2, 255)


def test_a_style_transition_does_not_change_the_overlay():
    # `transition` de estilo é carregada sem efeito: o overlay sai idêntico ao de um estilo sem
    # ela. A transição que o render consome é a do **plano** (`Shot.transition`), não a do estilo.
    from app.studio.adapters.render_plan_ffmpeg import caption_layout, overlay_colors

    plain = _resolved()
    with_transition = _resolved(transition={"kind": "fade", "duration_ticks": 40})
    assert caption_layout(VideoFormat.short, with_transition) == caption_layout(VideoFormat.short, plain)
    assert overlay_colors(with_transition) == overlay_colors(plain)


def test_resolved_style_carries_no_extra_bag():
    # `extra` é do agregado `VisualStyle`, não do retrato que o render consome: não há caminho
    # para um campo de extensão vazar para o executor pelo `ResolvedStyle`.
    assert not hasattr(_resolved(), "extra")
