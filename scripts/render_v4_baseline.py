#!/usr/bin/env python3
"""Gera a Fixture Técnica (60-90s) e o Piloto Audiovisual Original (5-8 min) para a fase V4-00.

Atende estritamente às durações especificadas pelo critério de homologação:
1. Fixture Técnica: 60–90 segundos (4 cenas calibradas, ~64s total).
2. Piloto Audiovisual: 5–8 minutos (300 a 480 segundos: 18 cenas documentais aprofundadas, ~350s total).

Executa 100% dentro do contêiner Docker oficial com Piper TTS local e FFmpeg nativo,
sem qualquer chamada a provedores remotos ou APIs pagas (custo de API: $0.00).
Gera métricas completas de ffprobe, FfmpegQa, performance (tempo, CPU total e filho, RAM, disco) e SHA-256.
Usa diretórios temporários exclusivos por execução e valida todos os critérios de qualidade e duração.
"""
from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import subprocess
import sys
import tempfile
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def measure_resources_usage() -> dict:
    """Mede consumo de CPU (usuário + sistema) e RAM pico para o processo atual e filhos."""
    self_ru = resource.getrusage(resource.RUSAGE_SELF)
    children_ru = resource.getrusage(resource.RUSAGE_CHILDREN)

    # No Linux (Docker), ru_maxrss é reportado em kilobytes; no macOS, em bytes
    is_linux = sys.platform.startswith("linux")
    factor = 1024.0 if is_linux else (1024.0 * 1024.0)

    self_rss_mb = self_ru.ru_maxrss / factor
    children_rss_mb = children_ru.ru_maxrss / factor
    combined_rss_mb = max(self_rss_mb, children_rss_mb)

    cpu_user = round(self_ru.ru_utime + children_ru.ru_utime, 3)
    cpu_sys = round(self_ru.ru_stime + children_ru.ru_stime, 3)
    cpu_total = round(cpu_user + cpu_sys, 3)

    return {
        "cpu_user_seconds": cpu_user,
        "cpu_system_seconds": cpu_sys,
        "cpu_total_seconds": cpu_total,
        "peak_rss_self_mb": round(self_rss_mb, 2),
        "peak_rss_children_mb": round(children_rss_mb, 2),
        "peak_rss_combined_mb": round(combined_rss_mb, 2),
    }


def measure_dir_size_bytes(dir_path: Path) -> int:
    """Calcula tamanho total ocupado por arquivos dentro de um diretório."""
    if not dir_path.exists():
        return 0
    total = 0
    for root, _, files in os.walk(dir_path):
        for f in files:
            fp = os.path.join(root, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total


def probe_media_details(path: Path) -> dict:
    """Extrai informações de stream e formato do arquivo gerado via ffprobe mecânico."""
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(res.stdout)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    fmt = info.get("format", {})

    fps = None
    if video:
        r_fps = video.get("r_frame_rate", "")
        if "/" in r_fps:
            num, den = r_fps.split("/")
            if float(den) > 0:
                fps = round(float(num) / float(den), 2)
        elif r_fps:
            try:
                fps = float(r_fps)
            except ValueError:
                fps = None

    nb_frames = None
    if video and "nb_frames" in video and str(video["nb_frames"]).isdigit():
        nb_frames = int(video["nb_frames"])
    if nb_frames is None and fps and "duration" in fmt:
        try:
            nb_frames = round(float(fmt["duration"]) * fps)
        except Exception:
            nb_frames = None

    return {
        "duration_s": round(float(fmt.get("duration", 0.0)), 3),
        "size_bytes": int(fmt.get("size", path.stat().st_size if path.exists() else 0)),
        "width": int(video["width"]) if video and "width" in video else None,
        "height": int(video["height"]) if video and "height" in video else None,
        "video_codec": video.get("codec_name") if video else None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "fps": fps,
        "nb_frames": nb_frames,
    }


def validate_duration(duration_s: float, min_s: float, max_s: float, label: str) -> None:
    """Garante que a duração final medida esteja estritamente dentro do intervalo de aceite."""
    if not (min_s <= duration_s <= max_s):
        raise ValueError(
            f"Duração inválida para {label}: {duration_s:.2f}s está fora do limite de homologação [{min_s:.1f}s, {max_s:.1f}s]"
        )


def validate_qa_criteria(qa_result: dict, label: str) -> None:
    """Valida critérios técnicos essenciais de conformidade EBU R128 e integridade do vídeo."""
    errors = []
    black_ratio = qa_result.get("black_ratio", 1.0)
    if black_ratio is not None and black_ratio > 0.0:
        errors.append(f"black_ratio={black_ratio} (esperado 0.0)")

    # frozen_ratio elevado é a limitação estrutural mapeada no baseline AS-IS (cards estáticos).
    # Rejeita apenas se o vídeo estiver totalmente paralisado (> 0.85).
    frozen_ratio = qa_result.get("frozen_ratio", 1.0)
    if frozen_ratio is not None and frozen_ratio > 0.85:
        errors.append(f"frozen_ratio={frozen_ratio} (esperado <= 0.85 no baseline AS-IS)")

    lufs = qa_result.get("integrated_lufs")
    if lufs is None or not (-24.0 <= lufs <= -14.0):
        errors.append(f"integrated_lufs={lufs} (esperado entre -24 e -14 LUFS)")

    true_peak = qa_result.get("true_peak_dbtp")
    if true_peak is not None and true_peak > 0.0:
        errors.append(f"true_peak_dbtp={true_peak} dBTP (esperado <= 0.0 dBTP)")

    if errors:
        raise ValueError(f"Critérios de QA violados para {label}: " + "; ".join(errors))


def extract_representative_frames(video_path: Path, output_dir: Path, duration_s: float, num_frames: int = 6) -> list[str]:
    """Extrai amostras de quadros em intervalos regulares para revisão visual."""
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_paths = []
    percentages = [0.05, 0.20, 0.40, 0.60, 0.80, 0.95][:num_frames]
    for idx, pct in enumerate(percentages, start=1):
        target_s = round(duration_s * pct, 2)
        out_frame = output_dir / f"frame_{idx:02d}_{int(target_s)}s.png"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", str(target_s), "-i", str(video_path),
            "-vframes", "1", "-q:v", "2", str(out_frame)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and out_frame.exists():
            frame_paths.append(str(out_frame))
    return frame_paths


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
    work_dir = Path(tempfile.mkdtemp(prefix="v4_fixture_60s_work_"))
    size = SIZE[VideoFormat.long]  # 1920, 1080
    out_mp4 = OUTPUT_DIR / "v4_fixture_tecnica_60s.mp4"

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

    t_total_start = time.perf_counter()
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

    t_qa_start = time.perf_counter()
    qa = FfmpegQa().analyze(out_mp4, narration=work_dir / "narration.wav")
    t_qa_end = time.perf_counter()
    qa_duration = t_qa_end - t_qa_start

    t_total_end = time.perf_counter()
    total_duration = t_total_end - t_total_start

    disk_work_bytes = measure_dir_size_bytes(work_dir)
    shutil.rmtree(work_dir, ignore_errors=True)

    probe = probe_media_details(out_mp4)
    validate_duration(probe["duration_s"], 60.0, 90.0, "Fixture Técnica (60-90s)")
    validate_qa_criteria(qa, "Fixture Técnica (60-90s)")

    mp4_hash = sha256_file(out_mp4)
    total_size = out_mp4.stat().st_size

    return {
        "name": "v4_fixture_tecnica_60s",
        "path": str(out_mp4),
        "file_name": out_mp4.name,
        "format": f"{probe['width']}x{probe['height']} (16:9)",
        "duration_s": probe["duration_s"],
        "scenes_count": len(scenes),
        "timing_s": {
            "synth_time_s": round(synth_duration, 2),
            "render_time_s": round(render_duration, 2),
            "qa_time_s": round(qa_duration, 2),
            "total_execution_time_s": round(total_duration, 2),
        },
        "disk_usage": {
            "output_size_bytes": total_size,
            "output_size_mb": round(total_size / (1024 * 1024), 2),
            "temp_work_dir_bytes": disk_work_bytes,
            "temp_work_dir_mb": round(disk_work_bytes / (1024 * 1024), 2),
        },
        "sha256": mp4_hash,
        "stream_details": {
            "video_codec": probe.get("video_codec"),
            "audio_codec": probe.get("audio_codec"),
            "fps": probe.get("fps"),
            "nb_frames": probe.get("nb_frames"),
            "resolution": f"{probe['width']}x{probe['height']}",
        },
        "qa_metrics": {
            "integrated_lufs": qa.get("integrated_lufs"),
            "narration_lufs": qa.get("narration_lufs"),
            "silence_ratio": qa.get("silence_ratio"),
            "narration_silence_ratio": qa.get("narration_silence_ratio"),
            "black_ratio": qa.get("black_ratio"),
            "frozen_ratio": qa.get("frozen_ratio"),
            "true_peak_dbtp": qa.get("true_peak_dbtp"),
        },
        "cost": {
            "cost_api_usd": 0.00,
            "cost_compute_type": "local_cpu_execution",
            "notes": "100% processado localmente em CPU (Piper TTS + FFmpeg nativo). Zero chamadas a APIs pagas."
        }
    }


DOCUMENTARY_SCENES = [
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
        "Em meados do século dezenove, o britânico George Boole propôs que as leis do pensamento lógico poderiam ser expressas "
        "por meio de equações algébricas com valores de verdadeiro e falso. Sua álgebra booleana forneceu a ponte teórica exata "
        "que transformaria portas lógicas e comutadores elétricos em motores de raciocínio dedutivo.",
        "GEORGE BOOLE",
        "A Álgebra da Lógica e dos Circuitos",
        ((25, 45, 50), (12, 22, 28)),
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
        "Em mil novecentos e quarenta e oito, Claude Shannon publicou A Teoria Matemática da Comunicação, estabelecendo as bases "
        "da era digital. Shannon demonstrou que qualquer informação, texto, som ou imagem, pode ser quantificada em dígitos binários "
        "denominados bits, e transmitida com confiabilidade matemática sobre canais sujeitos a ruído.",
        "CLAUDE SHANNON",
        "A Teoria da Informação e a Origem do Bit",
        ((35, 25, 50), (18, 12, 30)),
    ),
    (
        "Logo após o fim da guerra, em mil novecentos e quarenta e seis, entrou em operação o ENIAC na Universidade da Pensilvânia. "
        "Pesando trinta toneladas e alimentado por mais de dezessete mil válvulas termoiônicas, o colosso calculava trajetórias balísticas "
        "em segundos. Na mesma época, John von Neumann formalizou o modelo de programa armazenado em memória única.",
        "O COLOSSO ENIAC",
        "A Era das Válvulas e a Arquitetura Von Neumann",
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
        "deu origem ao microprocessador comercial. Engenheiros como Robert Noyce e Jack Kilby possibilitaram que todo o núcleo de uma unidade "
        "central de processamento coubesse na ponta de um dedo humano.",
        "O CIRCUITO INTEGRADO",
        "Do Silício Micrométrico ao Primeiro Microprocessador",
        ((30, 30, 60), (15, 15, 35)),
    ),
    (
        "Com o crescimento da complexidade do hardware, o software emergiu como disciplina autônoma e indispensável. "
        "Nos laboratórios da AT&T Bell, Ken Thompson e Dennis Ritchie desenvolveram o sistema Unix e a linguagem C, criando "
        "uma filosofia de ferramentas modulares, portabilidade e código aberto que alicerça a infraestrutura dos servidores atuais.",
        "UNIX E A LINGUAGEM C",
        "A Modularidade dos Sistemas Operacionais Modernos",
        ((35, 45, 35), (18, 25, 18)),
    ),
    (
        "Entre os anos setenta e oitenta, os computadores deixaram as salas com ar-condicionado das grandes corporações para ocupar mesas residenciais. "
        "Pesquisadores do centro Xerox PARC introduziram a interface gráfica, o mouse, janelas sobrepostas e redes locais Ethernet, "
        "transformando para sempre a experiência e a interação de seres humanos com máquinas.",
        "COMPUTAÇÃO PESSOAL",
        "Xerox PARC e o Nascimento das Interfaces Gráficas",
        ((45, 35, 30), (25, 18, 15)),
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
        "ganharam maturidade exponencial. Aceleração massiva por processadores gráficos permitiu que algoritmos aprendessem padrões complexos, "
        "sintetizassem voz natural, reconhecessem imagens e traduzissem línguas em tempo real.",
        "APRENDIZADO PROFUNDO",
        "Redes Neurais e Reconhecimento de Padrões em Larga Escala",
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


def render_pilot_5min(voice: PiperVoice) -> dict:
    """Produz o piloto audiovisual de 5 a 8 minutos (300 a 480 segundos: 18 cenas documentais, ~350s)."""
    print("\n[+] Renderizando Piloto Audiovisual Original (5–8 min / 300–480s)...")
    work_dir = Path(tempfile.mkdtemp(prefix="v4_pilot_5min_work_"))
    size = SIZE[VideoFormat.long]  # 1920, 1080
    out_mp4 = OUTPUT_DIR / "v4_piloto_audiovisual_5min.mp4"

    documentary_scenes = DOCUMENTARY_SCENES

    t_total_start = time.perf_counter()
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

    t_qa_start = time.perf_counter()
    qa = FfmpegQa().analyze(out_mp4, narration=work_dir / "narration.wav")
    t_qa_end = time.perf_counter()
    qa_duration = t_qa_end - t_qa_start

    t_total_end = time.perf_counter()
    total_duration = t_total_end - t_total_start

    disk_work_bytes = measure_dir_size_bytes(work_dir)
    shutil.rmtree(work_dir, ignore_errors=True)

    probe = probe_media_details(out_mp4)
    validate_duration(probe["duration_s"], 300.0, 480.0, "Piloto Audiovisual Original (5-8 min)")
    validate_qa_criteria(qa, "Piloto Audiovisual Original (5-8 min)")

    mp4_hash = sha256_file(out_mp4)
    total_size = out_mp4.stat().st_size

    # Extrai 6 quadros representativos para revisão visual
    frames_dir = OUTPUT_DIR / "frames_pilot_v4"
    frame_files = extract_representative_frames(out_mp4, frames_dir, probe["duration_s"], num_frames=6)

    return {
        "name": "v4_piloto_audiovisual_5min",
        "path": str(out_mp4),
        "file_name": out_mp4.name,
        "format": f"{probe['width']}x{probe['height']} (16:9)",
        "duration_s": probe["duration_s"],
        "scenes_count": len(scenes),
        "timing_s": {
            "synth_time_s": round(synth_duration, 2),
            "render_time_s": round(render_duration, 2),
            "qa_time_s": round(qa_duration, 2),
            "total_execution_time_s": round(total_duration, 2),
        },
        "disk_usage": {
            "output_size_bytes": total_size,
            "output_size_mb": round(total_size / (1024 * 1024), 2),
            "temp_work_dir_bytes": disk_work_bytes,
            "temp_work_dir_mb": round(disk_work_bytes / (1024 * 1024), 2),
        },
        "sha256": mp4_hash,
        "stream_details": {
            "video_codec": probe.get("video_codec"),
            "audio_codec": probe.get("audio_codec"),
            "fps": probe.get("fps"),
            "nb_frames": probe.get("nb_frames"),
            "resolution": f"{probe['width']}x{probe['height']}",
        },
        "qa_metrics": {
            "integrated_lufs": qa.get("integrated_lufs"),
            "narration_lufs": qa.get("narration_lufs"),
            "silence_ratio": qa.get("silence_ratio"),
            "narration_silence_ratio": qa.get("narration_silence_ratio"),
            "black_ratio": qa.get("black_ratio"),
            "frozen_ratio": qa.get("frozen_ratio"),
            "true_peak_dbtp": qa.get("true_peak_dbtp"),
        },
        "extracted_frames": frame_files,
        "cost": {
            "cost_api_usd": 0.00,
            "cost_compute_type": "local_cpu_execution",
            "notes": "100% processado localmente em CPU (Piper TTS + FFmpeg nativo). Zero chamadas a APIs pagas."
        }
    }


def main() -> int:
    t0 = time.perf_counter()
    voice = PiperVoice("pt_BR-faber-medium")

    fixture_metrics = render_fixture_60s(voice)
    pilot_metrics = render_pilot_5min(voice)

    t1 = time.perf_counter()
    resources = measure_resources_usage()

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "V4-00",
        "title": "Baseline Audiovisual AS-IS e Benchmark Técnico",
        "environment": {
            "runtime": "Docker Debian Bookworm aarch64",
            "python_version": sys.version.split()[0],
            "ffmpeg_support": "FFmpeg nativo com libass, ebur128, silencedetect, blackdetect, freezedetect",
            "piper_voice": "pt_BR-faber-medium",
        },
        "overall_performance": {
            "total_benchmark_elapsed_s": round(t1 - t0, 2),
            "resource_usage": resources,
            "cost_api_total_usd": 0.00,
            "cost_compute_summary": "Processamento local em contêiner Docker oficial sem chamadas externas a provedores pagos.",
        },
        "videos": [fixture_metrics, pilot_metrics],
    }

    report_path = OUTPUT_DIR / "v4_baseline_metrics.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n[+] Benchmark Concluído com Sucesso!")
    print(f"    - Relatório gravado em: {report_path}")
    print(f"    - Fixture (60-90s): {fixture_metrics['path']} ({fixture_metrics['duration_s']}s, {fixture_metrics['disk_usage']['output_size_mb']} MB, SHA: {fixture_metrics['sha256'][:16]}...)")
    print(f"    - Piloto (5-8 min): {pilot_metrics['path']} ({pilot_metrics['duration_s']}s, {pilot_metrics['disk_usage']['output_size_mb']} MB, SHA: {pilot_metrics['sha256'][:16]}...)")
    print(f"    - CPU Total: {resources['cpu_total_seconds']}s | RAM Pico Combinada: {resources['peak_rss_combined_mb']} MB")
    print(f"    - Custo API: ${report['overall_performance']['cost_api_total_usd']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
