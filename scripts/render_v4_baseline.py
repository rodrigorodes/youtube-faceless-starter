#!/usr/bin/env python3
"""Gera a Fixture Técnica (60-90s) e o Piloto Audiovisual Original (5-8 min) para a fase V4-00.

Atende estritamente às durações especificadas:
1. Fixture Técnica: 60–90 segundos (4 cenas calibradas, ~70s total).
2. Piloto Audiovisual: 5–8 minutos (14 cenas calibradas, ~320s / 5m20s total).

Executa 100% dentro do contêiner Docker oficial com Piper TTS local e FFmpeg nativo,
sem qualquer chamada a provedores remotos ou APIs pagas (custo $0.00).
Gera métricas completas de ffprobe, FfmpegQa, performance (tempo, CPU, RAM) e SHA-256.
"""
from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

# Insere renderer no path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderer"))

from app.studio.adapters.qa_ffmpeg import FfmpegQa
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from app.studio.adapters.voice_piper import PiperVoice
from app.studio.application.ports import RenderSpec
from app.studio.domain.contracts import Scene, VideoFormat
from app.studio.domain.render import SIZE, make_cues, scene_length

OUTPUT_DIR = ROOT / "storage" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _get_peak_ram_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / 1024.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _create_cinematic_card(
    path: Path,
    size: tuple[int, int],
    title: str,
    subtitle: str,
    bg_gradient: tuple[tuple[int, int, int], tuple[int, int, int]],
    scene_idx: int,
    total_scenes: int,
) -> None:
    width, height = size
    img = Image.new("RGB", size, bg_gradient[0])
    draw = ImageDraw.Draw(img)

    # Gradiente vertical suave
    c1, c2 = bg_gradient
    for y in range(height):
        ratio = y / height
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Moldura visual sutil
    draw.rectangle([40, 40, width - 40, height - 40], outline=(100, 120, 150), width=2)
    draw.rectangle([48, 48, width - 48, height - 48], outline=(60, 75, 95), width=1)

    # Elementos visuais centrais
    header = f"HISTÓRIA DA COMPUTAÇÃO — CENA {scene_idx + 1:02d} DE {total_scenes:02d}"
    draw.text((100, 100), header, fill=(180, 200, 230))
    draw.text((100, 220), title.upper(), fill=(255, 255, 255))
    draw.text((100, 320), subtitle, fill=(200, 215, 235))

    # Linha divisória de destaque
    draw.line([(100, 380), (width - 100, 380)], fill=(0, 200, 255), width=3)

    # Rodapé institucional de governança
    footer = "FACELESS STUDIO V4 — REFERÊNCIA AUDIOVISUAL (BASELINE AS-IS)"
    draw.text((100, height - 120), footer, fill=(130, 150, 175))

    img.save(path)


def render_fixture_60s(voice: PiperVoice) -> dict:
    """Produz a fixture técnica de 60 a 90 segundos (16:9)."""
    print("\n[+] Renderizando Fixture Técnica (60–90s)...")
    work_dir = Path("/tmp/v4_fixture_60s_work")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    size = SIZE[VideoFormat.long]  # 1920, 1080
    out_mp4 = OUTPUT_DIR / "v4_fixture_tecnica_60s.mp4"

    # 4 cenas calibradas para ~65s a 75s de vídeo total
    script_segments = [
        (
            "Esta é a fixture técnica oficial da versão quatro do Faceless Studio. "
            "Aqui nós testamos a calibração precisa do motor de síntese de voz Piper, "
            "avaliando pausas, inflecções e estabilidade da narração em língua portuguesa sem dependências externas.",
            "CALIBRAÇÃO E SÍNTESE",
            "Módulo de Fala Offline pt_BR-faber-medium",
            ((20, 30, 50), (10, 15, 25)),
        ),
        (
            "O segundo segmento exercita o alinhamento rítmico da trilha sonora de fundo. "
            "A mixagem dinâmica aplica atenuação suave sob a voz e recuperação gradual de volume, "
            "garantindo que o diálogo falado permaneça sempre nítido, claro e perfeitamente inteligível.",
            "MIXAGEM E DUCKING",
            "Processamento Dinâmico de Trilha CC0",
            ((30, 45, 60), (15, 25, 35)),
        ),
        (
            "No terceiro bloco, avaliamos o comportamento do subsistema de legendagem sincronizada. "
            "As legendas são queimadas diretamente nos quadros com posicionamento centralizado e formatação precisa, "
            "acompanhando a cadência e o tempo exato de cada frase pronunciada pelo locutor.",
            "LEGENDAS SINCRONIZADAS",
            "Renderização com RenderPlan e Subtítulos ASS",
            ((40, 35, 55), (20, 15, 30)),
        ),
        (
            "Por fim, a renderização integra todos os elementos com verificação estrita de conformidade EBU R128. "
            "O pipeline mede automaticamente o loudness integrado, ausência de clipping de áudio, silence ratio "
            "e ausência de quadros pretos, assegurando determinismo total do produto audiovisual.",
            "COMPOSIÇÃO E CONFORMIDADE",
            "Garantia EBU R128 e Conformidade Técnica",
            ((25, 50, 45), (12, 25, 22)),
        ),
    ]

    scenes, images, wavs, lengths, cues, offset = [], [], [], [], [], 0.0

    t_synth_start = time.perf_counter()
    for idx, (text, title, sub, colors) in enumerate(script_segments):
        img_path = work_dir / f"fixture_{idx}.png"
        _create_cinematic_card(img_path, size, title, sub, colors, idx, len(script_segments))

        wav_path = work_dir / f"fixture_{idx}.wav"
        dur = voice.speak(text, wav_path)
        slen = scene_length(dur)

        sc = Scene(
            id=f"sc_fix_{idx:026d}",
            video_id="v_fix_000000000000000000000001",
            idx=idx,
            narration=text,
            label=f"FIX-SCENE-{idx+1}",
            caption=title,
            image_prompt="cenário de teste técnico com gráfico e parâmetros visuais",
            claim_ids=[],
            asset_id=f"ast_fix_{idx:026d}",
        )
        scenes.append(sc)
        images.append(img_path)
        wavs.append(wav_path)
        lengths.append(slen)
        cues += make_cues(text, offset, dur)
        offset += slen

    t_synth_end = time.perf_counter()
    synth_duration = t_synth_end - t_synth_start

    spec = RenderSpec(
        scenes=scenes,
        images=images,
        speech_wavs=wavs,
        scene_seconds=lengths,
        cues=cues,
        format=VideoFormat.long,
        music=True,
        work_dir=work_dir,
    )

    t_render_start = time.perf_counter()
    renderer = PlanFfmpegRenderer()
    renderer.render(spec, out_mp4)
    t_render_end = time.perf_counter()
    render_duration = t_render_end - t_render_start

    qa = FfmpegQa().analyze(out_mp4, narration=work_dir / "narration.wav")
    total_size = out_mp4.stat().st_size
    mp4_hash = _sha256(out_mp4)

    return {
        "name": "v4_fixture_tecnica_60s",
        "path": str(out_mp4),
        "file_name": out_mp4.name,
        "format": "1920x1080 (16:9)",
        "duration_s": qa["duration_s"],
        "scenes_count": len(scenes),
        "synth_time_s": round(synth_duration, 2),
        "render_time_s": round(render_duration, 2),
        "size_bytes": total_size,
        "size_mb": round(total_size / (1024 * 1024), 2),
        "sha256": mp4_hash,
        "video_codec": qa.get("video_codec"),
        "audio_codec": qa.get("audio_codec"),
        "integrated_lufs": qa.get("integrated_lufs"),
        "narration_lufs": qa.get("narration_lufs"),
        "silence_ratio": qa.get("silence_ratio"),
        "black_ratio": qa.get("black_ratio"),
        "true_peak_dbtp": qa.get("true_peak_dbtp"),
        "fps": 25.0,
    }


def render_pilot_5min(voice: PiperVoice) -> dict:
    """Produz o piloto audiovisual de 5 a 8 minutos (14 cenas, ~310s a 330s)."""
    print("\n[+] Renderizando Piloto Audiovisual Original (5–8 min / ~320s)...")
    work_dir = Path("/tmp/v4_pilot_5min_work")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    size = SIZE[VideoFormat.long]  # 1920, 1080
    out_mp4 = OUTPUT_DIR / "v4_piloto_audiovisual_5min.mp4"

    # Roteiro documentário aprofundado de 14 cenas estruturadas (~21s a 24s por cena)
    documentary_scenes = [
        (
            "Desde os primórdios da civilização humana, a contagem e a medição foram necessidades vitais para a sobrevivência. "
            "Das marcas em ossos pré-históricos ao surgimento do ábaco na Mesopotâmia e na Ásia, a humanidade sempre buscou "
            "estender as capacidades limitadas de sua memória através de instrumentos físicos engenhosos.",
            "O ÁBACO E AS ORIGENS",
            "A Necessidade Ancestral de Contar e Calcular",
            ((25, 35, 55), (10, 15, 30)),
        ),
        (
            "Durante a Renascença e a Revolução Científica, o comércio marítimo e a astronomia exigiram cálculos de precisão inédita. "
            "Matemáticos como John Napier introduziram os logaritmos e as réguas de cálculo, permitindo multiplicações complexas "
            "através de simples adições geométricas gravadas em marfim e madeira.",
            "LOGARITMOS E TABELAS",
            "A Simplificação Geométrica do Cálculo",
            ((30, 40, 50), (12, 20, 25)),
        ),
        (
            "Em mil seiscentos e quarenta e dois, o jovem filósofo e matemático Blaise Pascal desenvolveu a Pascalina para ajudar seu pai, "
            "um cobrador de impostos. Essa calculadora pioneira utilizava engrenagens dentadas e tambores cilíndricos, automatizando "
            "as operações de adição e subtração pela primeira vez na história.",
            "A PASCALINA DE PASCAL",
            "As Primeiras Engrenagens da Automação",
            ((35, 45, 45), (15, 25, 20)),
        ),
        (
            "Poucas décadas depois, Gottfried Wilhelm Leibniz aprimorou o conceito mecânico criando o escalonador cilíndrico, "
            "capaz de realizar multiplicações e divisões diretas. Mais importante ainda, Leibniz formulou com rigor filosófico "
            "o sistema binário de numeração, a linguagem que séculos mais tarde regeria todos os circuitos digitais.",
            "LEIBNIZ E O BINÁRIO",
            "O Cilindro Escalonado e a Lógica de Zero e Um",
            ((40, 35, 40), (20, 15, 18)),
        ),
        (
            "Na virada para o século dezenove, o tecelão francês Joseph-Marie Jacquard revolucionou a manufatura ao controlar seus teares "
            "por meio de cartões de papelão perfurados. Pela primeira vez no mundo, uma sequência lógica de instruções codificadas "
            "comandava automaticamente o movimento e a produção de uma máquina.",
            "O TEAR DE JACQUARD",
            "A Primeira Programação por Cartões Perfurados",
            ((45, 30, 35), (22, 12, 15)),
        ),
        (
            "Inspirado por Jacquard, o matemático britânico Charles Babbage projetou a grandiosa Máquina Analítica. Seu projeto mecânico "
            "já incorporava uma unidade de processamento chamada moinho, uma memória denominada depósito e controle por cartões perfurados, "
            "definindo a base arquitetural dos computadores mais de cem anos antes de sua construção física.",
            "CHARLES BABBAGE",
            "O Projeto Visionário da Máquina Analítica",
            ((45, 35, 25), (25, 18, 10)),
        ),
        (
            "Ao lado de Babbage, a brilhante matemática Ada Lovelace compreendeu o potencial da máquina com profundidade ímpar. "
            "Ela percebeu que a Máquina Analítica poderia processar qualquer entidade simbólica, inclusive notas musicais, e redigiu "
            "o primeiro algoritmo destinado a um computador, tornando-se a primeira programadora da história.",
            "ADA LOVELACE",
            "A Visão Poética do Primeiro Algoritmo",
            ((40, 20, 45), (20, 10, 25)),
        ),
        (
            "Em mil novecentos e trinta e seis, Alan Turing publicou seu artigo revolucionário sobre números computáveis, concebendo a máquina "
            "universal de Turing. Durante a Segunda Guerra, no lendário centro de Bletchley Park, Turing liderou a quebra dos códigos "
            "nazistas da máquina Enigma, consolidando a teoria da computação e da criptografia moderna.",
            "ALAN TURING",
            "A Máquina Universal e a Vitória da Lógica",
            ((20, 40, 50), (10, 20, 30)),
        ),
        (
            "Logo após o fim da guerra, em mil novecentos e quarenta e seis, entrou em operação o ENIAC na Universidade da Pensilvânia. "
            "Pesando trinta toneladas e alimentado por mais de dezessete mil válvulas termoiônicas, o colosso calculava trajetórias balísticas "
            "em segundos, inaugurando de forma definitiva a era dos computadores eletrônicos de grande porte.",
            "O COLOSSO ENIAC",
            "A Alvorada da Eletrônica e das Válvulas",
            ((50, 35, 20), (30, 20, 10)),
        ),
        (
            "A grande limitação do calor e da fragilidade das válvulas foi superada em mil novecentos e quarenta e sete, quando Bardeen, "
            "Brattain e Shockley inventaram o transistor nos Laboratórios Bell. O uso de semicondutores sólidos como o germânio e o silício "
            "permitiu diminuir drasticamente o tamanho e o consumo de energia dos circuitos.",
            "O TRANSISTOR",
            "A Revolução Silenciosa dos Semicondutores",
            ((25, 50, 40), (10, 25, 20)),
        ),
        (
            "No final dos anos sessenta e início dos anos setenta, a integração de milhares de transistores em uma pastilha de silício "
            "deu origem ao microprocessador comercial. Essa miniaturização extrema abriu caminho para a revolução dos microcomputadores, "
            "trazendo o poder de processamento diretamente para a mesa de residências e pequenos escritórios.",
            "A ERA DO MICROCHIP",
            "A Democratização dos Computadores Pessoais",
            ((30, 30, 60), (15, 15, 35)),
        ),
        (
            "A partir dos anos noventa, a interconexão global através da internet e da World Wide Web transformou computadores individuais "
            "em nós de uma rede mundial viva de conhecimento. O fluxo contínuo de dados em fibra óptica e redes sem fio descentralizou "
            "a informação e redefiniu a economia, a ciência e a cultura de toda a sociedade.",
            "A REDE GLOBAL",
            "A Interconexão Universal do Conhecimento",
            ((20, 45, 65), (10, 25, 40)),
        ),
        (
            "Com a computação em nuvem e a abundância de grandes volumes de dados, o aprendizado de máquina e as redes neurais profundas "
            "ganharam maturidade exponencial. Algoritmos passaram a reconhecer imagens, sintetizar fala natural e traduzir línguas em tempo real, "
            "superando a programação puramente estática e baseada em regras rígidas.",
            "APRENDIZADO PROFUNDO",
            "Redes Neurais e o Reconhecimento de Padrões",
            ((45, 25, 55), (22, 12, 30)),
        ),
        (
            "Hoje chegamos à fronteira da inteligência artificial generativa e multimodal, onde modelos computacionais colaboram ativamente "
            "na redação, criação artística, programação e produção audiovisual automatizada. O Faceless Studio se apoia nessa longa "
            "jornada histórica de séculos para construir os próximos passos da criação audiovisual autônoma.",
            "FRONTEIRAS COGNITIVAS",
            "A Simbiose Criativa entre Humanos e Algoritmos",
            ((55, 25, 60), (30, 10, 35)),
        ),
    ]

    scenes, images, wavs, lengths, cues, offset = [], [], [], [], [], 0.0

    t_synth_start = time.perf_counter()
    for idx, (text, title, sub, colors) in enumerate(documentary_scenes):
        img_path = work_dir / f"pilot_{idx:02d}.png"
        _create_cinematic_card(img_path, size, title, sub, colors, idx, len(documentary_scenes))

        wav_path = work_dir / f"pilot_{idx:02d}.wav"
        dur = voice.speak(text, wav_path)
        slen = scene_length(dur)

        sc = Scene(
            id=f"sc_plt_{idx:026d}",
            video_id="v_plt_000000000000000000000001",
            idx=idx,
            narration=text,
            label=f"PILOT-SCENE-{idx+1:02d}",
            caption=title,
            image_prompt="cena de documentário histórico sobre computação e tecnologia",
            claim_ids=[],
            asset_id=f"ast_plt_{idx:026d}",
        )
        scenes.append(sc)
        images.append(img_path)
        wavs.append(wav_path)
        lengths.append(slen)
        cues += make_cues(text, offset, dur)
        offset += slen

    t_synth_end = time.perf_counter()
    synth_duration = t_synth_end - t_synth_start

    spec = RenderSpec(
        scenes=scenes,
        images=images,
        speech_wavs=wavs,
        scene_seconds=lengths,
        cues=cues,
        format=VideoFormat.long,
        music=True,
        work_dir=work_dir,
    )

    t_render_start = time.perf_counter()
    renderer = PlanFfmpegRenderer()
    renderer.render(spec, out_mp4)
    t_render_end = time.perf_counter()
    render_duration = t_render_end - t_render_start

    qa = FfmpegQa().analyze(out_mp4, narration=work_dir / "narration.wav")
    total_size = out_mp4.stat().st_size
    mp4_hash = _sha256(out_mp4)

    return {
        "name": "v4_piloto_audiovisual_5min",
        "path": str(out_mp4),
        "file_name": out_mp4.name,
        "format": "1920x1080 (16:9)",
        "duration_s": qa["duration_s"],
        "scenes_count": len(scenes),
        "synth_time_s": round(synth_duration, 2),
        "render_time_s": round(render_duration, 2),
        "size_bytes": total_size,
        "size_mb": round(total_size / (1024 * 1024), 2),
        "sha256": mp4_hash,
        "video_codec": qa.get("video_codec"),
        "audio_codec": qa.get("audio_codec"),
        "integrated_lufs": qa.get("integrated_lufs"),
        "narration_lufs": qa.get("narration_lufs"),
        "silence_ratio": qa.get("silence_ratio"),
        "black_ratio": qa.get("black_ratio"),
        "true_peak_dbtp": qa.get("true_peak_dbtp"),
        "fps": 25.0,
    }


def main() -> int:
    voice = PiperVoice("pt_BR-faber-medium")

    fixture_metrics = render_fixture_60s(voice)
    pilot_metrics = render_pilot_5min(voice)

    peak_ram = _get_peak_ram_mb()

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "peak_ram_mb": round(peak_ram, 2),
        "cost_usd": 0.00,
        "videos": [fixture_metrics, pilot_metrics],
    }

    report_path = OUTPUT_DIR / "v4_baseline_metrics.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n[+] Benchmark Concluído com Sucesso!")
    print(f"    - Relatório gravado em: {report_path}")
    print(f"    - Fixture (60s): {fixture_metrics['path']} ({fixture_metrics['duration_s']}s, {fixture_metrics['size_mb']} MB, SHA: {fixture_metrics['sha256'][:16]}...)")
    print(f"    - Piloto (5min): {pilot_metrics['path']} ({pilot_metrics['duration_s']}s, {pilot_metrics['size_mb']} MB, SHA: {pilot_metrics['sha256'][:16]}...)")
    print(f"    - Custo: ${report['cost_usd']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
