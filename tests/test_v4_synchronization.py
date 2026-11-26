"""Testes de conformidade para V4-07 — Synchronization & Captions.

Valida as atividades V4-07.01 a V4-07.12:
- V4-07.01: Preservação de renderização ASS nativa.
- V4-07.02 / V4-07.04 / V4-07.05: Alinhamento por palavra, tags karaoke e highlight.
- V4-07.06 / V4-07.07: Estilos por canal (CaptionStyleConfig) e Safe Area para Shorts.
- V4-07.08: Detecção e resolução automática de sobreposição temporal entre legendas.
- V4-07.09: Exportação para SRT e WebVTT (export_captions).
- V4-07.10 / V4-07.11: Detecção de drift e recálculo da timeline com mudança de duração da voz.
- V4-07.12: Correção manual de cues pelo operador.
"""
from __future__ import annotations

import pytest

from app.studio.adapters.captions_ass import AssSubtitleRenderer
from app.studio.adapters.captions_exporters import (
    SrtSubtitleRenderer,
    VttSubtitleRenderer,
    export_captions,
)
from app.studio.domain.captions import (
    CaptionLine,
    CaptionOverlapError,
    CaptionStyleConfig,
    WordTiming,
    apply_manual_caption_edits,
    check_audio_caption_sync,
    recalculate_caption_timeline,
    resolve_overlaps,
    validate_no_overlaps,
)
from app.studio.domain.contracts import VideoFormat


@pytest.fixture
def sample_captions() -> list[CaptionLine]:
    w1 = WordTiming(word="O", start_ms=0, duration_ms=200)
    w2 = WordTiming(word="algoritmo", start_ms=200, duration_ms=600)
    w3 = WordTiming(word="executa", start_ms=800, duration_ms=500)
    line1 = CaptionLine(start_ms=0, end_ms=1300, text="O algoritmo executa", words=(w1, w2, w3))

    w4 = WordTiming(word="com", start_ms=1300, duration_ms=200)
    w5 = WordTiming(word="precisão", start_ms=1500, duration_ms=700)
    line2 = CaptionLine(start_ms=1300, end_ms=2200, text="com precisão", words=(w4, w5))

    return [line1, line2]


class TestCustomStylesAndSafeArea:
    """V4-07.01, V4-07.06, V4-07.07: Estilos customizados e margens seguras."""

    def test_custom_style_in_ass_renderer(self, sample_captions):
        custom_style = CaptionStyleConfig(
            font_name="Montserrat",
            font_size=72,
            primary_color="&H0000FFFF",  # Amarelo
            secondary_color="&H00FF00FF",  # Magenta
            outline_color="&H00111111",
            outline_width=6,
            shadow_depth=2,
            margin_v=320,  # Safe margin acima dos botões de Shorts
            alignment=2,
        )

        ass = AssSubtitleRenderer.render(
            lines=sample_captions,
            format=VideoFormat.short,
            style=custom_style,
        )

        assert "Montserrat" in ass
        assert ",72,&H0000FFFF,&H00FF00FF,&H00111111,&H00000000,1,0,0,0,100,100,0,0,1,6,2,2,10,10,320,1" in ass
        assert "Dialogue: 0,0:00:00.00,0:00:01.30,Default,,0,0,0,,{\\k20}O {\\k60}algoritmo {\\k50}executa" in ass

    def test_default_safe_margin_for_shorts(self, sample_captions):
        ass = AssSubtitleRenderer.render(lines=sample_captions, format="short")
        # Por padrão, margin_v deve ser 280 para shorts para proteger botões nativos
        assert ",280,1" in ass


class TestOverlapValidationAndResolution:
    """V4-07.08: Validação e mitigação de sobreposição temporal."""

    def test_validate_no_overlaps_success(self, sample_captions):
        # sample_captions é contíguo (1300 == 1300) -> sem erro
        validate_no_overlaps(sample_captions)

    def test_validate_no_overlaps_raises_on_collision(self):
        line1 = CaptionLine(start_ms=0, end_ms=1500, text="Linha um")
        line2 = CaptionLine(start_ms=1200, end_ms=2500, text="Linha dois")  # Colisão de 300ms

        with pytest.raises(CaptionOverlapError, match="Overlap detected between caption 0"):
            validate_no_overlaps([line1, line2])

    def test_resolve_overlaps_adjusts_boundaries(self):
        line1 = CaptionLine(start_ms=0, end_ms=1500, text="Linha um")
        line2 = CaptionLine(start_ms=1200, end_ms=2500, text="Linha dois")

        resolved = resolve_overlaps([line1, line2])
        assert len(resolved) == 2
        # O fim de line1 deve ter sido ajustado para 1200
        assert resolved[0].end_ms == 1200
        assert resolved[1].start_ms == 1200
        assert resolved[1].end_ms == 2500
        # Validar que agora passa no validador estrito
        validate_no_overlaps(resolved)


class TestExportersSrtAndVtt:
    """V4-07.09: Exportação para SRT e WebVTT."""

    def test_srt_export(self, sample_captions):
        srt = SrtSubtitleRenderer.render(sample_captions)
        expected = (
            "1\n00:00:00,000 --> 00:00:01,300\nO algoritmo executa\n\n"
            "2\n00:00:01,300 --> 00:00:02,200\ncom precisão\n"
        )
        assert srt == expected

    def test_vtt_export(self, sample_captions):
        vtt = VttSubtitleRenderer.render(sample_captions)
        assert vtt.startswith("WEBVTT\n\n")
        assert "1\n00:00:00.000 --> 00:00:01.300\nO algoritmo executa" in vtt
        assert "2\n00:00:01.300 --> 00:00:02.200\ncom precisão" in vtt

    def test_export_captions_polymorphic(self, sample_captions):
        ass = export_captions(sample_captions, format_type="ass", video_format="short")
        assert "[Script Info]" in ass

        srt = export_captions(sample_captions, format_type="srt")
        assert "-->" in srt and "," in srt

        vtt = export_captions(sample_captions, format_type="vtt")
        assert "WEBVTT" in vtt and "." in vtt

        with pytest.raises(ValueError, match="Unsupported caption export format"):
            export_captions(sample_captions, format_type="invalid")  # type: ignore


class TestSyncDriftAndTimelineRecalculation:
    """V4-07.10, V4-07.11: Medição de drift e recálculo da timeline."""

    def test_check_audio_caption_sync(self, sample_captions):
        # sample_captions termina em 2200ms
        res_ok = check_audio_caption_sync(sample_captions, audio_duration_ms=2350, max_drift_ms=300)
        assert res_ok["synced"] is True
        assert res_ok["drift_ms"] == 150

        res_drift = check_audio_caption_sync(sample_captions, audio_duration_ms=3000, max_drift_ms=300)
        assert res_drift["synced"] is False
        assert res_drift["drift_ms"] == 800

    def test_recalculate_caption_timeline_scale(self, sample_captions):
        # A voz foi acelerada ou desacelerada (de 2200ms para 4400ms -> dobro)
        recalculated = recalculate_caption_timeline(
            sample_captions,
            original_duration_ms=2200,
            target_duration_ms=4400,
        )

        assert len(recalculated) == 2
        assert recalculated[0].start_ms == 0
        assert recalculated[0].end_ms == 2600
        assert recalculated[0].words[0].duration_ms == 400
        assert recalculated[0].words[1].duration_ms == 1200
        assert recalculated[1].start_ms == 2600
        assert recalculated[1].end_ms == 4400


class TestManualCorrections:
    """V4-07.12: Correção manual de legendas pelo operador."""

    def test_apply_manual_caption_edits(self, sample_captions):
        edits = {
            1: {"text": "com máxima precisão e confiabilidade", "end_ms": 2500}
        }
        edited = apply_manual_caption_edits(sample_captions, edits)
        assert len(edited) == 2
        assert edited[0].text == "O algoritmo executa"
        assert edited[1].text == "com máxima precisão e confiabilidade"
        assert edited[1].end_ms == 2500

        # Imutabilidade da lista original preservada
        assert sample_captions[1].text == "com precisão"
