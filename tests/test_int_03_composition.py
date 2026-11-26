"""Testes de Integração e Estabilização — Onda INT-03 (Composição Audiovisual e Compilador).

Valida os achados A03, A04 e A06 da auditoria INT-01:
- A03: MAX_OVERLAYS_PER_SCENE ampliado para até 8 camadas simultâneas por cena.
- A04: LayerExecution transporta opacidade, escala e posições x/y; _overlay_filter
  compila filtros FFmpeg com escala e colorchannelmixer para transparência;
  _fade_filter suporta transição crossfade.
- A06: Métricas de áudio rotulam claramente sample_peak_dbfs com alias compatível.
"""
import pytest

from app.studio.application.render_compiler import (
    MAX_OVERLAYS_PER_SCENE,
    CompileError,
    LayerExecution,
)
from app.studio.adapters.render_plan_compiler import (
    _fade_filter,
    _layer_dict,
    _overlay_filter,
)
from app.studio.domain.render_plan import Transition
from app.studio.domain.audio_dsp import generate_synthetic_tone, mix_multitrack_pcm
from app.studio.domain.audio_catalog import AudioCategory
from app.studio.domain.audio_multitrack import AudioEvent, MultitrackAudioPlan


def test_int_03_max_overlays_per_scene_elevated():
    """A03: O compilador agora suporta até 8 camadas simultâneas por cena."""
    assert MAX_OVERLAYS_PER_SCENE == 8


def test_int_03_layer_execution_carries_transformations():
    """A04: LayerExecution transporta escala, opacidade e posições x e y."""
    layer = LayerExecution(
        shot_id="shot_pip_01",
        asset_id="asset_logo",
        media_type="image",
        source="/tmp/logo.png",
        z_index=2,
        start_ticks=0,
        duration_ticks=60,
        fit="contain",
        opacity=0.75,
        scale=0.35,
        position_x=0.85,
        position_y=0.15,
    )

    assert layer.opacity == 0.75
    assert layer.scale == 0.35
    assert layer.position_x == 0.85
    assert layer.position_y == 0.15

    # Serialização do dicionário do shot preserva as transformações
    d = _layer_dict(layer)
    assert d["opacity"] == 0.75
    assert d["scale"] == 0.35
    assert d["position_x"] == 0.85
    assert d["position_y"] == 0.15


def test_int_03_overlay_filter_generates_scale_and_opacity():
    """A04: _overlay_filter aplica scale, opacidade (colorchannelmixer) e coordenadas relativas."""
    layer_pip = LayerExecution(
        shot_id="shot_pip_02",
        asset_id="asset_watermark",
        media_type="image",
        source="/tmp/watermark.png",
        z_index=2,
        start_ticks=30,
        duration_ticks=90,
        fit="contain",
        opacity=0.60,
        scale=0.5,
        position_x=0.90,
        position_y=0.10,
    )

    # 1080x1920 (Short 9:16)
    flt = _overlay_filter(layer_pip, number=3, width=1080, height=1920, tps=30, previous="b0")

    # Deve conter colorchannelmixer com alfa 0.60
    assert "colorchannelmixer=aa=0.60" in flt
    # Deve conter scale dimensionado (1080 * 0.5 = 540)
    assert "scale=540:960" in flt
    # Deve posicionar com offset calculado e enable na janela temporal
    assert "overlay=" in flt
    assert "enable='gte(t,1.000)*lt(t,4.000)'" in flt


def test_int_03_fade_filter_supports_crossfade():
    """A04: _fade_filter compila transição crossfade sem rejeitar com CompileError."""
    transition_cross = Transition(
        kind="crossfade",
        duration_ticks=15,  # 0.5s a 30 tps
    )

    # 3.0 segundos a 30 tps
    fade_str = _fade_filter(transition_cross, seconds=3.0, tps=30, shot_id="shot_01")
    assert "fade=t=out:st=2.500:d=0.500" in fade_str


def test_int_03_audio_metrics_labeling():
    """A06: Métricas de mixagem rotulam sample_peak_dbfs e mantêm compatibilidade."""
    tone_pcm = generate_synthetic_tone(duration_s=1.0, freq_hz=440.0, gain_db=-6.0)

    event = AudioEvent(
        id="ev_01",
        track_id="test_tone",
        category=AudioCategory.SFX,
        start_s=0.0,
        duration_s=1.0,
        gain_db=-3.0,
    )
    plan = MultitrackAudioPlan(total_duration_s=1.0, sfx_events=(event,))

    samples, metrics = mix_multitrack_pcm(plan, {"test_tone": tone_pcm})
    assert len(samples) > 0
    assert "sample_peak_dbfs" in metrics
    assert "true_peak_dbtp" in metrics
    assert metrics["sample_peak_dbfs"] == metrics["true_peak_dbtp"]
    assert metrics["is_clipped"] is False
