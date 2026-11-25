"""RP-010 / V4-00 — Testes de regressão para precisão de ticks e contiguidade de legendas.

Valida as alterações em domain/render.py (make_cues) e domain/render_plan_builder.py (_subtitle_cues):
1. Identidade binária exata de pontos de corte em float entre chunks consecutivos (make_cues).
2. Não sobreposição estrita de ticks inteiros (start_tick >= prev_end) na timeline de legendas.
3. Respeito rigoroso aos limites temporais de início (offset + LEAD), narração e término da cena.
4. Construção completa de RenderPlan com 18 cenas documentais densas sem erro de overlap.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from app.studio.domain.contracts import VideoFormat
from app.studio.domain.pacing import PacingPreset
from app.studio.domain.render import LEAD, Cue, make_cues
from app.studio.domain.render_plan import (
    AssetReference,
    AudioMix,
    StyleSnapshot,
    Timebase,
)
from app.studio.domain.render_plan_builder import (
    StoryboardScene,
    _subtitle_cues,
    build_render_plan,
)
from app.studio.domain.ticks import seconds_to_ticks, ticks_to_seconds


# --------------------------------------------------------------------------- #
# 1. Testes de make_cues (domain/render.py)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("speech_seconds", [1.0, 5.5, 14.2, 19.145, 10.0 / 3.0, 37.8921])
@pytest.mark.parametrize("offset", [0.0, 10.5, 73.123456, 180.0])
def test_make_cues_binary_continuity_between_chunks(speech_seconds: float, offset: float):
    """Garante que cue[i].end é exatamente igual a cue[i+1].start em ponto flutuante IEEE-754."""
    text = (
        "O ábaco surgiu na Mesopotâmia antiga como a primeira ferramenta "
        "mecânica para registrar cálculos numéricos rápidos e confiáveis. "
        "Ele demonstrou que a humanidade podia terceirizar a aritmética."
    )
    cues = make_cues(text, start=offset, speech_seconds=speech_seconds, max_chars=35)
    assert len(cues) > 1

    # Início deve ser exatamente offset + LEAD
    assert math.isclose(cues[0].start, offset + LEAD, abs_tol=1e-9)

    # Fim da última cue deve ser exatamente offset + LEAD + speech_seconds
    assert math.isclose(cues[-1].end, offset + LEAD + speech_seconds, abs_tol=1e-9)

    # Continuidade exata entre todas as cues consecutivas
    for i in range(len(cues) - 1):
        assert cues[i].end == cues[i + 1].start, (
            f"Descontinuidade encontrada no índice {i}: "
            f"cues[{i}].end={cues[i].end!r} != cues[{i+1}].start={cues[i+1].start!r}"
        )


def test_make_cues_single_word_and_short_texts():
    """Valida comportamento para textos curtos ou palavra única."""
    cues = make_cues("Computação", start=0.0, speech_seconds=2.0)
    assert len(cues) == 1
    assert math.isclose(cues[0].start, LEAD, abs_tol=1e-9)
    assert math.isclose(cues[0].end, LEAD + 2.0, abs_tol=1e-9)


def test_make_cues_empty_text():
    """Texto vazio não gera cues."""
    assert make_cues("", start=0.0, speech_seconds=2.0) == []


# --------------------------------------------------------------------------- #
# 2. Testes de _subtitle_cues (domain/render_plan_builder.py)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("tps", [24, 25, 30, 60, 25000])
@pytest.mark.parametrize("speech_seconds", [0.8, 2.5, 7.333, 14.2, 19.145, 45.67])
@pytest.mark.parametrize("offset_s", [0.0, 0.333, 15.0, 73.628374, 300.123])
def test_subtitle_cues_strict_no_overlap_across_rates(tps: int, speech_seconds: float, offset_s: float):
    """Garante que a conversão seconds -> ticks NUNCA produz overlap entre cues consecutivas."""
    text = (
        "Blaise Pascal construiu a Pascalina em 1642 para ajudar seu pai, "
        "um cobrador de impostos. Usando engrenagens de latão cuidadosamente "
        "talhadas, a máquina realizava somas e subtrações com transporte mecânico."
    )
    scene = StoryboardScene(
        scene_id="scene_test",
        asset_id="asset_test",
        narration=text,
        speech_seconds=speech_seconds,
    )

    cues = _subtitle_cues(scene, offset_s=offset_s, speech=speech_seconds, tps=tps)
    assert len(cues) > 1

    for i in range(len(cues)):
        cue = cues[i]
        # Duração deve ser de no mínimo 1 tick
        assert cue.duration_ticks >= 1, f"Cue {i} possui duração zero ou negativa: {cue}"

        # Se houver cue anterior, o início da atual deve ser >= término da anterior
        if i > 0:
            prev_cue = cues[i - 1]
            prev_end = prev_cue.start_tick + prev_cue.duration_ticks
            assert cue.start_tick >= prev_end, (
                f"Overlap detectado no TPS={tps} entre cue {i-1} e {i}: "
                f"cue[{i-1}] termina em {prev_end}, mas cue[{i}] inicia em {cue.start_tick}"
            )


def test_subtitle_cues_boundary_limits():
    """Garante que as cues de legenda ficam contidas no envelope da cena."""
    tps = 25
    offset_s = 10.0
    speech_s = 5.0
    scene = StoryboardScene(
        scene_id="scene_bound",
        asset_id="asset_bound",
        narration="Testando os limites da legenda com relação ao tempo de narração e cena.",
        speech_seconds=speech_s,
    )

    cues = _subtitle_cues(scene, offset_s=offset_s, speech=speech_s, tps=tps)
    scene_start_tick = seconds_to_ticks(offset_s, tps)
    narration_end_tick = seconds_to_ticks(offset_s + LEAD + speech_s, tps)

    # Primeira cue não pode iniciar antes de offset_s + LEAD (em ticks)
    assert cues[0].start_tick >= seconds_to_ticks(offset_s + LEAD, tps)

    # Última cue não deve ultrapassar significativamente o final da narração (+1 tick tolerância de arredondamento)
    assert cues[-1].start_tick + cues[-1].duration_ticks <= narration_end_tick + 2


# --------------------------------------------------------------------------- #
# 3. Teste Integrado: RenderPlan com 18 cenas densas (Piloto V4)
# --------------------------------------------------------------------------- #

def test_build_render_plan_18_scenes_no_timeline_overlap():
    """Monta um RenderPlan real com 18 cenas documentais e valida que a Timeline do plano não lança erro."""
    scenes_text = [
        "O ábaco surgiu na Mesopotâmia antiga como a primeira ferramenta mecânica de cálculo.",
        "Blaise Pascal construiu a Pascalina em 1642 usando engrenagens de latão com transporte.",
        "Gottfried Leibniz expandiu a automação aritmética com o cilindro de passos dentados.",
        "Joseph Marie Jacquard introduziu cartões perfurados para programar teares têxteis em 1804.",
        "Charles Babbage projetou o Engenho Analítico, a primeira máquina computacional universal.",
        "Ada Lovelace compreendeu que o motor de Babbage podia manipular símbolos e compôs o primeiro algoritmo.",
        "George Boole estabeleceu a álgebra binária mapeando a lógica formal em valores de zero e um.",
        "Herman Hollerith automatizou o censo americano de 1890 com tabuladores elétricos e cartões.",
        "Alan Turing formalizou o conceito de máquina universal e desvendou códigos cifrados na guerra.",
        "Claude Shannon unificou a teoria da informação com circuitos de comutação eletrônica em 1937.",
        "O ENIAC entrou em operação em 1945 realizando milhares de multiplicações com válvulas a vácuo.",
        "John von Neumann consolidou a arquitetura de programa armazenado em memória única compartilhada.",
        "A invenção do transistor no Bell Labs em 1947 substituiu válvulas frágeis por semicondutores.",
        "O circuito integrado permitiu agrupar milhares de transistores em uma pastilha de silício puro.",
        "O microprocessador Intel 4004 em 1971 miniaturizou uma unidade central inteira em um componente.",
        "A computação pessoal e as interfaces gráficas na década de setenta democratizaram as ferramentas.",
        "A ARPANET e a World Wide Web conectaram a humanidade em uma rede global instantânea de dados.",
        "Hoje os modelos de inteligência artificial aprendem padrões em escala transformando o conhecimento.",
    ]

    tps = 25
    scenes = []
    assets = []

    for idx, text in enumerate(scenes_text):
        aid = f"asset_{idx:02d}"
        scenes.append(StoryboardScene(
            scene_id=f"scene_{idx:02d}",
            asset_id=aid,
            narration=text,
            speech_seconds=15.0 + (idx % 4),  # Duração variada: 15s, 16s, 17s, 18s
            label=f"CENA {idx + 1}",
        ))
        assets.append(AssetReference(
            asset_id=aid,
            asset_version=1,
            uri=f"/data/assets/{aid}.png",
            content_sha256="a" * 64,
            media_type="image",
            license="CC0",
        ))

    plan = build_render_plan(
        plan_id="plan:regression-18-scenes",
        revision=1,
        project_id="a" * 32,
        video_id="b" * 32,
        format=VideoFormat.long,
        scenes=scenes,
        assets=assets,
        timebase=Timebase(ticks_per_second=tps),
        style_snapshot=StyleSnapshot(source="channel", style_id="default", version=1),
        pacing_preset=PacingPreset.balanced,
        audio_mix=AudioMix(music_gain=0.3),
    )

    # Se a Timeline aceitou o plano sem ValidationError de overlap, a invariante está garantida
    assert plan.schema_version == 2
    assert len(plan.timeline.tracks) >= 3

    subtitles = plan.timeline.subtitles
    assert len(subtitles) > 50  # Múltiplas cues distribuídas pelas 18 cenas

    # Valida contiguidade de todas as cues de legenda
    for i in range(len(subtitles) - 1):
        curr_cue = subtitles[i]
        next_cue = subtitles[i + 1]
        assert curr_cue.start_tick + curr_cue.duration_ticks <= next_cue.start_tick


# --------------------------------------------------------------------------- #
# 4. Teste Extremo de Densidade e Janela Temporal da Narração
# --------------------------------------------------------------------------- #

def test_subtitles_extreme_cues_prevented_from_exceeding_narration_window():
    """Valida o caso extremo onde a densidade de cues ameaça ultrapassar a janela da narração.

    Garante que:
    1. Em make_cues, a última cue respeita matematicamente o limite superior (offset + LEAD + speech_seconds).
    2. No domínio de ticks (RenderPlan), se a quantidade mínima de ticks requerida pelas cues
       (>= 1 tick por chunk) ultrapassar a janela disponível da narração/cena, o build_render_plan
       rejeita a montagem e impede que cues desincronizadas sejam aceitas.
    """
    text_extreme = "Palavra chave muito importante para ser testada em alta densidade. " * 30
    speech_short = 0.4  # Janela de fala muito curta (0.4s)
    offset = 1.0

    # 1. make_cues não ultrapassa a janela contínua em float
    cues_float = make_cues(text_extreme, start=offset, speech_seconds=speech_short)
    assert len(cues_float) > 10
    assert math.isclose(cues_float[-1].end, offset + LEAD + speech_short, abs_tol=1e-9)
    assert cues_float[-1].end <= offset + LEAD + speech_short + 1e-9

    # 2. Em ticks, múltiplos chunks a 1 tick cada exigiriam mais ticks que a narração/cena comportam
    scene = StoryboardScene(
        scene_id="scene_overflow",
        asset_id="asset_test",
        narration=text_extreme,
        speech_seconds=speech_short,
        label="CENA EXTREMA",
    )
    asset = AssetReference(
        asset_id="asset_test",
        asset_version=1,
        uri="/data/assets/asset_test.png",
        content_sha256="c" * 64,
        media_type="image",
        license="CC0",
    )

    with pytest.raises(Exception) as exc_info:
        build_render_plan(
            plan_id="plan:extreme-subtitles",
            revision=1,
            project_id="c" * 32,
            video_id="d" * 32,
            format=VideoFormat.long,
            scenes=[scene],
            assets=[asset],
            timebase=Timebase(ticks_per_second=25),
            style_snapshot=StyleSnapshot(source="channel", style_id="default", version=1),
            pacing_preset=PacingPreset.dynamic,
            audio_mix=AudioMix(music_gain=0.3),
        )

    # Comprova mecanicamente que o sistema impediu o plano inválido
    err_str = str(exc_info.value).lower()
    assert any(term in err_str for term in ("out of sync with the narration", "outside the scene", "alignment tolerance"))
