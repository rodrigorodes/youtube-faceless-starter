"""Testes de conformidade para V4-06 — Creative Intelligence.

Valida as atividades V4-06.01 a V4-06.12:
- V4-06.01 a V4-06.04: Direção narrativa em 3 atos, objetivo por cena e escala emocional (1-5).
- V4-06.05 a V4-06.07: Planejamento de shots (ShotIntent), sugestões de música, SFX e pacing.
- V4-06.08 / V4-06.09: Channel Identity congelada e auditável.
- V4-06.10: Overrides manuais do operador com aplicação limpa e determinística.
- V4-06.11: Sanitização estrita contra injeção de comandos FFmpeg/shell na saída do LLM.
- V4-06.18 / V4-06.19: Aceite formal (brief estruturado por cena, validado e editável, sem FFmpeg).
"""
from __future__ import annotations

import pytest

from renderer.app.studio.domain.creative_director import (
    ActKind,
    CreativeBrief,
    CreativeDirectorPlan,
    CreativeSecurityViolation,
    SceneCreativeDirection,
    ShotIntent,
)


def _create_sample_brief() -> CreativeBrief:
    return CreativeBrief(
        topic="A História Secreta de Alan Turing",
        narrative_goal="Revelar o impacto da quebra do Enigma e os fundamentos da ciência da computação.",
        hook="E se um único matemático britânico tivesse encurtado a Segunda Guerra Mundial em dois anos?",
        content_structure=("A Máquina Enigma e Bletchley Park", "O Legado Universal da Computação"),
        tone="Documental reflexivo, sério e envolvente",
        pacing="Ritmo cadenciado com momentos de suspense analítico",
        visual_direction="Cinematográfico, fotos históricas restauradas e esquemas lógicos",
        caption_strategy="Destaque em termos técnicos e datas chave",
        audio_guidance="Trilha ambiente de tensão orquestral e SFX de teletipo",
    )


class TestStructuredNarrativeAndDirection:
    """V4-06.01 a V4-06.07: Narrativa em atos, metas de cena, intensidade e shots."""

    def test_creative_brief_validation(self):
        brief = _create_sample_brief()
        assert brief.topic == "A História Secreta de Alan Turing"
        assert len(brief.content_structure) == 2

        with pytest.raises(ValueError, match="at least 2 sections"):
            CreativeBrief(
                topic="Tópico",
                narrative_goal="Objetivo",
                hook="Gancho",
                content_structure=("Apenas uma seção",),
                tone="Tom",
                pacing="Pacing",
                visual_direction="Visual",
                caption_strategy="Legendas",
                audio_guidance="Áudio",
            )

    def test_scene_creative_direction_and_acts(self):
        shot1 = ShotIntent(
            shot_index=0,
            visual_intent="Primeiro plano das engrenagens da máquina Enigma girando",
            framing="close_up",
            lighting="dramatic",
            suggested_motion="zoom_in",
        )
        shot2 = ShotIntent(
            shot_index=1,
            visual_intent="Visão geral de Alan Turing desenhando diagramas no quadro",
            framing="medium",
            lighting="natural",
            suggested_motion="pan_right",
        )

        direction = SceneCreativeDirection(
            scene_idx=1,
            act=ActKind.ACT_2_DEVELOPMENT,
            scene_goal="Explicar a complexidade criptográfica e o método de ataque da Bombe",
            emotional_intensity=4,
            visual_prompt_guide="Documentário histórico, iluminação volumétrica e mesas com fios",
            suggested_shots=(shot1, shot2),
            music_mood="suspense_analytical",
            sfx_cue="gear_click",
            pacing="fast",
        )

        assert direction.scene_idx == 1
        assert direction.act == ActKind.ACT_2_DEVELOPMENT
        assert direction.emotional_intensity == 4
        assert len(direction.suggested_shots) == 2
        assert direction.suggested_shots[0].framing == "close_up"

    def test_emotional_intensity_bounds(self):
        with pytest.raises(ValueError):
            SceneCreativeDirection(
                scene_idx=0,
                scene_goal="Objetivo",
                emotional_intensity=6,  # Máximo permitido é 5
                visual_prompt_guide="Guia visual",
            )

        with pytest.raises(ValueError):
            SceneCreativeDirection(
                scene_idx=0,
                scene_goal="Objetivo",
                emotional_intensity=0,  # Mínimo permitido é 1
                visual_prompt_guide="Guia visual",
            )


class TestSecuritySanitizationAgainstFfmpegInjection:
    """V4-06.11: Proibição estrita de comandos FFmpeg e shell na saída do LLM."""

    def test_reject_ffmpeg_injection_in_scene_goal(self):
        with pytest.raises((CreativeSecurityViolation, ValueError), match="inject FFmpeg commands"):
            SceneCreativeDirection(
                scene_idx=0,
                scene_goal="Exibir texto com ffmpeg -vf subtitles=sub.srt",
                emotional_intensity=3,
                visual_prompt_guide="Cena normal",
            )

    def test_reject_ffmpeg_injection_in_visual_prompt_guide(self):
        with pytest.raises((CreativeSecurityViolation, ValueError), match="inject FFmpeg commands"):
            SceneCreativeDirection(
                scene_idx=1,
                scene_goal="Apresentar resultado",
                emotional_intensity=3,
                visual_prompt_guide="Use -filter_complex overlay=10:10 para compor o vídeo",
            )

    def test_reject_shell_syntax_in_creative_brief(self):
        with pytest.raises((CreativeSecurityViolation, ValueError), match="forbidden low-level command"):
            CreativeBrief(
                topic="Tópico",
                narrative_goal="Objetivo",
                hook="Gancho",
                content_structure=("Seção 1", "Seção 2"),
                tone="Tom",
                pacing="Pacing",
                visual_direction="Execute sh -c rm -rf /data",
                caption_strategy="Legendas",
                audio_guidance="Áudio",
            )


class TestOperatorOverridesAndAcceptanceCriteria:
    """V4-06.10 e V4-06.19 (Aceite): Plano estruturado, identidade congelada e overrides."""

    def test_creative_director_plan_with_operator_overrides(self):
        brief = _create_sample_brief()
        sc1 = SceneCreativeDirection(
            scene_idx=0,
            act=ActKind.ACT_1_HOOK,
            scene_goal="Capturar a atenção imediata com o enigma",
            emotional_intensity=3,
            visual_prompt_guide="Visão sombria do Atlântico Norte durante a guerra",
            music_mood="dark_ocean",
            pacing="moderate",
        )
        sc2 = SceneCreativeDirection(
            scene_idx=1,
            act=ActKind.ACT_2_DEVELOPMENT,
            scene_goal="Apresentação do desafio matemático",
            emotional_intensity=2,
            visual_prompt_guide="Documentos criptográficos decifrados",
            music_mood="analytical",
            pacing="slow",
        )

        plan = CreativeDirectorPlan(
            topic=brief.topic,
            high_level_brief=brief,
            scene_directions=(sc1, sc2),
            channel_identity_digest="sha256:channel_history_doc_v1",
        )

        # 1. Direção original
        effective_0 = plan.get_effective_scene_direction(0)
        assert effective_0 is not None
        assert effective_0.emotional_intensity == 3
        assert effective_0.pacing == "moderate"

        # 2. O operador decide aumentar a intensidade emocional e acelerar o pacing da cena 0
        plan_modified = plan.with_override(0, {
            "emotional_intensity": 5,
            "pacing": "fast",
            "sfx_cue": "thunder_crack",
        })

        effective_modified = plan_modified.get_effective_scene_direction(0)
        assert effective_modified is not None
        assert effective_modified.emotional_intensity == 5
        assert effective_modified.pacing == "fast"
        assert effective_modified.sfx_cue == "thunder_crack"

        # Imutabilidade do plano original preservada
        assert plan.get_effective_scene_direction(0).emotional_intensity == 3

        # 3. Cena 1 não foi afetada pelo override
        assert plan_modified.get_effective_scene_direction(1).emotional_intensity == 2

        # 4. Aceite: identidade congelada presente
        assert plan_modified.channel_identity_digest == "sha256:channel_history_doc_v1"
