"""REC-04.02 (R11) — Documentário Real de 5–8 min (>=25 cenas) pelo Studio, Pareado com V4-00.

Executa um documentário horizontal 1080p real (300–480s, >= 25 cenas) sobre o mesmo tema
e linhagem de roteiro do baseline V4-00 ("História da Computação"), integralmente pelas
rotas HTTP do Studio (FastAPI TestClient + Postgres descartável + ProductionCoordinator +
PlanFfmpegRenderer + Piper pt_BR-faber-medium + FfmpegQualityEvaluator/FfmpegQa):

1. CreativeBrief via PUT /studio/videos/{id}/direction (propagado ao RenderPlan).
2. Fontes + Roteiro de 25 cenas editadas via POST /studio/videos/{id}/script/scenes/{idx}.
   (Rebaseline controlado documentado: V4-00 tinha 18 cenas em 345.80s; REC-04.02 expande
   a mesma linha cronológica para 25 cenas dentro da janela 300–480s conforme SESSION-HANDOFF §5.)
3. Importação real via POST /studio/videos/{id}/scenes/{sid}/media/import (licença CC0-1.0):
   - PNGs 1080p determinísticos em múltiplas cenas;
   - MP4s reais 1080p 25fps em movimento contínuo (cenas 2, 10 e 18) como mídia base (exercitando PRE-1);
   - Overlays/PiP: PNG gráfico (cena 0, pos=1 direita; cena 12, pos=1 direita) e MP4 PiP (cena 1, pos=2 esquerda),
     verificando P2-1 (não colisão com HUD/disclosure superior esquerdo).
   - Cenas finais (20..24) geradas localmente pelo AssetsHandler (placeholder:v4).
4. Run #1 via ProductionCoordinator -> pausa em WAITING_HUMAN (AWAITING_APPROVAL, sem autoaprovação).
5. Edição de UMA cena (Cena 15) + nova mídia PNG v2 -> Regeneração Seletiva Run #2:
   comprova reutilização integral de cache (fingerprint, sha256, uri, mtime_ns) das 24 cenas intocadas
   e mede economia real de tempo de parede (s e %).
6. V2-F7 Thumbnail Check: GET /studio/videos/{id}/thumbnail (PillowThumbnail 1280x720 JPEG <= 2MB)
   + validação de 3 opções distintas de thumbnail/título via VideoPackaging + PillowThumbnail.
7. QA real (ffprobe, ebur128 LUFS/dBTP, blackdetect, freezedetect, silencedetect, pixels, áudio/ducking,
   drift áudio-legenda), custo $0.00 no usage_ledger, kill switch BLOCKED (STUDIO_PUBLICATION_ENABLED=0),
   e comparação pareada com o baseline V4-00.
"""
from __future__ import annotations

import io
import json
import os
import resource
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest
from PIL import Image

from app.studio.adapters.postgres.editorial_repo import PostgresUsageRepository
from app.studio.adapters.postgres.render_plan_repo import PostgresRenderPlanRepository
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.adapters.qa_ffmpeg import FfmpegQa
from app.studio.adapters.thumbnail import PillowThumbnail
from app.studio.domain.packaging import (
    Chapter,
    PackagingVariant,
    SourceCitation,
    TitleClaim,
    VideoPackaging,
)
from app.studio.domain.quality import CHECK_CAPTION_SYNC, CHECK_OVERLAY
from app.studio.domain.render_cache import NodeId
from rec04_helpers import (
    audio_window_rms,
    compute_audio_caption_drift,
    extract_frame,
    git_info,
    image_stats,
    make_real_mp4,
    make_rich_png,
    make_studio_client,
    mean_abs_diff,
    needs_ffmpeg,
    needs_piper,
    piper_version,
    probe_full,
    sha256_file,
    tool_version,
    wav_rms_and_duration,
)

SOURCE_URL = "https://pt.wikipedia.org/wiki/Historia_da_computacao"
SOURCE_TEXT = (
    "Desde os primórdios da civilização humana, o ábaco na Mesopotâmia e na Ásia permitiu estender a memória de cálculo.\n"
    "Durante a Revolução Científica, John Napier apresentou os logaritmos e as réguas de cálculo para multiplicar por adições.\n"
    "Em 1642, Blaise Pascal inventou a Pascalina com engrenagens dentadas.\n"
    "Gottfried Leibniz construiu o escalonador cilíndrico e formalizou o sistema binário de zero e um.\n"
    "No século dezenove, Joseph-Marie Jacquard automatizou teares industriais com cartões de papelão perfurados.\n"
    "Charles Babbage projetou a Máquina Analítica com unidade aritmética e memória separadas.\n"
    "Ada Lovelace redigiu o primeiro algoritmo publicado para um computador programável.\n"
    "No século dezenove, George Boole mostrou que o raciocínio lógico obedece a equações algébricas simples.\n"
    "Nos Estados Unidos, Herman Hollerith usou cartões perfurados eletromecânicos no censo de 1890.\n"
    "Em 1936, Alan Turing definiu a máquina universal.\n"
    "Durante a Segunda Guerra Mundial, em Bletchley Park, Turing liderou a decifração da máquina Enigma.\n"
    "Em 1948, Claude Shannon publicou a Teoria da Informação e definiu o bit.\n"
    "O computador ENIAC entrou em operação na Pensilvânia com trinta toneladas e dezessete mil válvulas.\n"
    "John von Neumann formalizou o modelo de programa armazenado na mesma memória principal.\n"
    "Em 1947, o transistor surgiu nos Laboratórios Bell com semicondutores sólidos.\n"
    "Nos anos sessenta, Robert Noyce e Jack Kilby integraram circuitos em pastilhas de silício para microprocessadores.\n"
    "Nos Laboratórios Bell, Ken Thompson e Dennis Ritchie criaram o sistema Unix e a linguagem C.\n"
    "A rede ARPANET interligou universidades por comutação de pacotes com rotas alternativas.\n"
    "No centro Xerox PARC surgiram a interface gráfica, o mouse, janelas sobrepostas e redes Ethernet.\n"
    "Na década de oitenta, os microcomputadores pessoais invadiram escritórios e residências.\n"
    "Nos anos noventa, Tim Berners-Lee lançou a World Wide Web unindo hipertexto e protocolos abertos.\n"
    "Sistemas distribuídos coordenam milhares de servidores com replicação confiável e alta disponibilidade.\n"
    "A computação em nuvem converteu centros de dados físicos em infraestrutura elástica sob demanda.\n"
    "O aprendizado profundo com redes neurais permitiu síntese de fala natural e reconhecimento de imagens.\n"
    "Hoje, a inteligência artificial multimodal colabora na redação, programação e produção audiovisual.\n"
)

# 25 cenas na mesma linha cronológica do V4-00 ("História da Computação")
# ~24–28 palavras por cena -> ~14–16s cada -> ~360–390s total (estritamente 300–480s).
DOCUMENTARY_SCENES_25: list[dict[str, str]] = [
    {
        "narration": (
            "Desde os primórdios da civilização, contar e medir foram tarefas essenciais para a vida em comunidade. "
            "Do osso entalhado ao ábaco antigo, a humanidade criou instrumentos físicos engenhosos para ampliar a própria memória."
        ),
        "caption": "O ábaco e as origens do cálculo",
        "image_prompt": "Ilustração de ábaco antigo de madeira em mesa de estudo documental",
    },
    {
        "narration": (
            "Na Revolução Científica, a navegação marítima e a astronomia exigiram cálculos muito mais precisos e rápidos. "
            "John Napier apresentou os logaritmos e réguas de cálculo, convertendo multiplicações difíceis em adições simples."
        ),
        "caption": "Logaritmos de John Napier",
        "image_prompt": "Réguas de cálculo históricas e tábuas logarítmicas em estilo técnico",
    },
    {
        "narration": (
            "Em mil seiscentos e quarenta e dois, Blaise Pascal inventou a Pascalina para auxiliar seu pai cobrador de impostos. "
            "Suas engrenagens dentadas automatizavam somas e subtrações, aliviando o trabalho exaustivo de contadores."
        ),
        "caption": "1642: a Pascalina de Blaise Pascal",
        "image_prompt": "Mecanismo interno de engrenagens metálicas da calculadora Pascalina",
    },
    {
        "narration": (
            "Décadas depois, Gottfried Leibniz construiu o escalonador cilíndrico para multiplicar diretamente com precisão mecânica "
            "e formalizou o sistema binário de zero e um que hoje sustenta toda a eletrônica moderna."
        ),
        "caption": "Gottfried Leibniz e o sistema binário",
        "image_prompt": "Diagrama do cilindro escalonado de Leibniz com notação binária",
    },
    {
        "narration": (
            "Na virada do século dezenove, Joseph-Marie Jacquard automatizou teares industriais com cartões perfurados resistentes. "
            "Uma sequência codificada de furos passou a comandar padrões complexos de tecido sem intervenção manual constante."
        ),
        "caption": "Cartões perfurados de Jacquard",
        "image_prompt": "Cartões perfurados de papelão guiando um tear mecânico industrial",
    },
    {
        "narration": (
            "Inspirado por Jacquard, Charles Babbage projetou a Máquina Analítica com notável visão de engenharia. "
            "Seu desenho incluía unidade aritmética e memória separadas, antecipando a estrutura essencial dos computadores atuais."
        ),
        "caption": "Máquina Analítica de Charles Babbage",
        "image_prompt": "Projeto mecânico detalhado da Máquina Analítica em bronze e aço",
    },
    {
        "narration": (
            "Ao lado de Babbage, Ada Lovelace compreendeu que máquinas poderiam manipular símbolos gerais muito além de simples números "
            "e redigiu o primeiro algoritmo publicado para um computador programável de propósito geral."
        ),
        "caption": "Ada Lovelace e o primeiro algoritmo",
        "image_prompt": "Manuscrito histórico com algoritmo matemático e notas de Ada Lovelace",
    },
    {
        "narration": (
            "Em meados do século dezenove, George Boole mostrou que o raciocínio lógico obedece a equações algébricas simples "
            "com valores de verdadeiro e falso, lançando a base matemática das futuras portas lógicas digitais."
        ),
        "caption": "Lógica algébrica de George Boole",
        "image_prompt": "Esquema visual de portas lógicas booleanas com sinais binários",
    },
    {
        "narration": (
            "Nos Estados Unidos, Herman Hollerith usou cartões perfurados eletromecânicos no censo de mil oitocentos e noventa, "
            "reduzindo anos de apuração estatística manual para poucos meses de processamento automatizado."
        ),
        "caption": "1890: Herman Hollerith e cartões perfurados",
        "image_prompt": "Máquina tabuladora eletromecânica com pilhas de cartões perfurados",
    },
    {
        "narration": (
            "Em mil novecentos e trinta e seis, Alan Turing definiu a máquina universal em um artigo histórico fundamental, "
            "estabelecendo com rigor matemático os limites teóricos do que qualquer algoritmo pode computar."
        ),
        "caption": "1936: a máquina universal de Alan Turing",
        "image_prompt": "Fita simbólica infinita representando a máquina universal de Alan Turing",
    },
    {
        "narration": (
            "Durante a Segunda Guerra Mundial, em Bletchley Park, Turing liderou a decifração secreta da máquina Enigma, "
            "acelerando decisivamente o nascimento da criptografia moderna e da própria computação eletrônica."
        ),
        "caption": "Bletchley Park e a máquina Enigma",
        "image_prompt": "Rotores criptográficos e decifradores eletromecânicos em Bletchley Park",
    },
    {
        "narration": (
            "Em mil novecentos e quarenta e oito, Claude Shannon publicou a Teoria da Informação com impacto duradouro, "
            "definindo o bit como unidade fundamental para transmitir dados com confiabilidade sobre canais ruidosos."
        ),
        "caption": "1948: Claude Shannon e o bit",
        "image_prompt": "Ondas de sinal digital e fluxo de bits em canal de comunicação",
    },
    {
        "narration": (
            "Logo após a guerra, o computador ENIAC entrou em operação na Pensilvânia com trinta toneladas e dezessete mil "
            "válvulas brilhantes, executando cálculos balísticos complexos em apenas poucos segundos."
        ),
        "caption": "ENIAC e a era das válvulas",
        "image_prompt": "Sala ampla com painéis de válvulas termoiônicas e cabos do ENIAC",
    },
    {
        "narration": (
            "Na mesma época, John von Neumann formalizou o modelo elegante de programa armazenado, permitindo que instruções "
            "e dados compartilhassem exatamente a mesma memória principal de acesso rápido."
        ),
        "caption": "Arquitetura de John von Neumann",
        "image_prompt": "Diagrama claro da arquitetura de Von Neumann entre processador e memória",
    },
    {
        "narration": (
            "Em mil novecentos e quarenta e sete, o transistor surgiu nos Laboratórios Bell com materiais inovadores. "
            "Semicondutores sólidos substituíram válvulas frágeis, reduzindo drasticamente calor, tamanho físico e consumo elétrico."
        ),
        "caption": "1947: o transistor nos Laboratórios Bell",
        "image_prompt": "Primeiro transistor semicondutor em laboratório de física aplicada",
    },
    {
        "narration": (
            "Nos anos sessenta, Robert Noyce e Jack Kilby integraram circuitos inteiros em minúsculas pastilhas de silício, "
            "abrindo caminho definitivo para microprocessadores completos na ponta de um dedo humano."
        ),
        "caption": "Pastilhas de silício e microprocessadores",
        "image_prompt": "Pastilha de silício com trilhas microscópicas iluminadas em estúdio",
    },
    {
        "narration": (
            "Nos Laboratórios Bell, Ken Thompson e Dennis Ritchie criaram o sistema Unix e a linguagem C com design limpo, "
            "consolidando ferramentas modulares e portabilidade entre diferentes arquiteturas de hardware."
        ),
        "caption": "Sistema Unix e a linguagem C",
        "image_prompt": "Terminal clássico monocromático exibindo código estruturado em linguagem C",
    },
    {
        "narration": (
            "Paralelamente, a rede ARPANET interligou universidades americanas por comutação de pacotes distribuída, provando "
            "que mensagens fragmentadas podiam atravessar rotas alternativas com resiliência e segurança."
        ),
        "caption": "ARPANET e comutação de pacotes",
        "image_prompt": "Mapa de nós interconectados da rede ARPANET com rotas redundantes",
    },
    {
        "narration": (
            "No centro Xerox PARC, pesquisadores criaram a interface gráfica intuitiva, o mouse, janelas sobrepostas e redes "
            "Ethernet, mudando para sempre a experiência cotidiana de interação humana com computadores."
        ),
        "caption": "Xerox PARC e redes Ethernet",
        "image_prompt": "Estação de trabalho pioneira com janelas gráficas e mouse mecânico",
    },
    {
        "narration": (
            "Na década de oitenta, os microcomputadores pessoais invadiram escritórios e residências, transformando máquinas "
            "antes restritas a grandes corporações em ferramentas acessíveis de trabalho e criação."
        ),
        "caption": "Microcomputadores pessoais nos anos oitenta",
        "image_prompt": "Computador pessoal clássico dos anos oitenta em mesa de escritório",
    },
    {
        "narration": (
            "Nos anos noventa, Tim Berners-Lee lançou a World Wide Web, unindo hipertexto e protocolos abertos para conectar "
            "documentos públicos, pesquisa científica e comércio em escala verdadeiramente planetária."
        ),
        "caption": "Tim Berners-Lee e a World Wide Web",
        "image_prompt": "Globo conectado por feixes de fibra óptica e hiperlinks digitais",
    },
    {
        "narration": (
            "Com o crescimento acelerado da rede, sistemas distribuídos passaram a coordenar milhares de servidores em paralelo, "
            "garantindo replicação confiável, consistência de dados e alta disponibilidade contínua."
        ),
        "caption": "Sistemas distribuídos e replicação",
        "image_prompt": "Arquitetura de cluster com múltiplos servidores sincronizados em rede",
    },
    {
        "narration": (
            "A computação em nuvem converteu centros de dados físicos em infraestrutura elástica sob demanda, permitindo que "
            "equipes pequenas e independentes implantassem serviços globais em poucos minutos."
        ),
        "caption": "Computação em nuvem sob demanda",
        "image_prompt": "Data center moderno com racks iluminados e fluxo contínuo de dados",
    },
    {
        "narration": (
            "Impulsionado por grandes volumes de dados e placas gráficas rápidas, o aprendizado profundo permitiu que redes "
            "neurais reconhecessem imagens complexas, traduzissem idiomas e sintetizassem fala natural."
        ),
        "caption": "Aprendizado profundo e redes neurais",
        "image_prompt": "Visualização de camadas profundas de uma rede neural artificial",
    },
    {
        "narration": (
            "Hoje, a inteligência artificial multimodal colabora ativamente na redação, programação e produção audiovisual "
            "automatizada, coroando séculos de engenhosidade matemática, eletrônica e algorítmica."
        ),
        "caption": "Fronteiras da inteligência artificial multimodal",
        "image_prompt": "Estúdio criativo moderno integrando código, áudio e imagem digital",
    },
]

SCENE_15_V2 = {
    "narration": (
        "A integração em silício evoluída por Noyce e Kilby multiplicou transistores por milímetro quadrado com precisão, "
        "permitindo que microprocessadores completos impulsionassem computadores pessoais e servidores modernos."
    ),
    "caption": "Silício, microprocessadores e servidores",
    "image_prompt": "Microprocessador moderno em silício com trilhas douradas de alta densidade",
}


def _baseline_v4_00_reference() -> dict:
    """Lê referência V4-00 real se disponível no checkout; caso contrário usa valores publicados em V4-00-BASELINE-REPORT.md."""
    metrics_path = Path("storage/output/runs/run_20261126_132447_198e47cb/v4_baseline_metrics.json")
    if metrics_path.is_file():
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        pilot = next((v for v in data.get("videos", []) if v.get("name") == "v4_piloto_audiovisual_5min"), None)
        if pilot:
            return {
                "source": str(metrics_path),
                "run_id": data.get("run_id"),
                "duration_s": pilot["duration_s"],
                "scenes_count": pilot["scenes_count"],
                "sha256": pilot["sha256"],
                "integrated_lufs": pilot["qa_metrics"]["integrated_lufs"],
                "true_peak_dbtp": pilot["qa_metrics"]["true_peak_dbtp"],
                "frozen_ratio": pilot["qa_metrics"]["frozen_ratio"],
                "silence_ratio": pilot["qa_metrics"]["silence_ratio"],
                "black_ratio": pilot["qa_metrics"]["black_ratio"],
                "total_execution_time_s": pilot["timing_s"]["total_execution_time_s"],
                "render_time_s": pilot["timing_s"]["render_time_s"],
                "qa_time_s": pilot["timing_s"]["qa_time_s"],
                "cost_api_usd": pilot["cost"]["cost_api_usd"],
                "resource_usage": data.get("overall_performance", {}).get("resource_usage", {}),
            }
    return {
        "source": "docs/backlogs/professional-audiovisual-v4/phases/V4-00-BASELINE-REPORT.md",
        "run_id": "run_20261126_132447_198e47cb",
        "duration_s": 345.8,
        "scenes_count": 18,
        "sha256": "48886a202a8b3ae205d9e0681019786b269a65455dbcb40de3f5c7ed14e70756",
        "integrated_lufs": -15.6,
        "true_peak_dbtp": -1.3,
        "frozen_ratio": 0.4937,
        "silence_ratio": 0.0,
        "black_ratio": 0.0,
        "total_execution_time_s": 126.28,
        "render_time_s": 85.34,
        "qa_time_s": 24.01,
        "cost_api_usd": 0.0,
        "resource_usage": {},
    }


@pytest.mark.rec04_documentary
@needs_ffmpeg
@needs_piper
def test_rec_04_02_real_documentary_5_8min_paired_with_v4_00(conn, dsn, tmp_path: Path):
    """REC-04.02: Documentário 5–8 min (>=25 cenas) via Studio HTTP + Piper + FFmpeg + QA + V2-F7 + Regressão Seletiva."""
    t_suite_start = time.monotonic()
    stage_timings: dict[str, float] = {}

    assert len(DOCUMENTARY_SCENES_25) == 25
    out_dir_env = os.environ.get("REC04_DOC_OUT_DIR")
    out_dir = Path(out_dir_env) if out_dir_env else None
    run_label = os.environ.get("REC04_DOC_RUN_ID", "pytest_rec04_doc")

    storage_root = tmp_path / "studio_storage"
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    studio, client = make_studio_client(dsn, storage_root, source_allowlist=("pt.wikipedia.org",))
    try:
        # 1. Projeto, Vídeo e CreativeBrief (PUT /direction)
        t0 = time.monotonic()
        proj_resp = client.post("/studio/projects", json={"name": "Piloto Documentário REC-04.02"})
        assert proj_resp.status_code == 201, proj_resp.text
        project_id = proj_resp.json()["id"]

        vid_resp = client.post(
            "/studio/videos",
            json={
                "project_id": project_id,
                "topic": "A História da Computação: Da Mecânica aos Cérebros de Silício",
                "format": "long",
                "target_duration_s": 360,
            },
        )
        assert vid_resp.status_code == 201, vid_resp.text
        video_id = vid_resp.json()["id"]

        dir_resp = client.put(
            f"/studio/videos/{video_id}/direction",
            json={
                "brief": {
                    "schema_version": 1,
                    "topic": "A História da Computação: Da Mecânica aos Cérebros de Silício",
                    "narrative_goal": "Documentar os 25 marcos históricos da computação com rigor factual",
                    "hook": "Como ferramentas mecânicas evoluíram até sistemas inteligentes em escala global?",
                    "content_structure": [
                        "Ato I: Instrumentos mecânicos e lógica simbólica (Cenas 1–9)",
                        "Ato II: Computação teórica, válvulas e silício (Cenas 10–17)",
                        "Ato III: Redes globais, nuvem e IA multimodal (Cenas 18–25)",
                    ],
                    "tone": "informativo",
                    "pacing": "cinematic",
                    "visual_direction": "documentário tecnológico cinematográfico com B-rolls em movimento",
                    "recommended_media_types": ["image", "video"],
                    "caption_strategy": "Palavra ativa com realce via ASS único (PRE-1)",
                    "audio_guidance": "Trilha sonora ambiente com ducking equilibrado",
                    "max_budget_usd": 0.0,
                    "quality_criteria": ["1080p 25fps", "LUFS -16", "True Peak <= -1.0 dBTP", "Licença CC0-1.0"],
                }
            },
        )
        assert dir_resp.status_code == 200, dir_resp.text

        # 2. Fonte e Roteiro de 25 cenas pelas rotas HTTP do Studio
        src_resp = client.post(
            f"/studio/videos/{video_id}/sources",
            json={"url": SOURCE_URL, "text": SOURCE_TEXT},
        )
        assert src_resp.status_code == 201, src_resp.text

        script_resp = client.post(f"/studio/videos/{video_id}/script", json={"scene_count": 20})
        assert script_resp.status_code == 201, script_resp.text
        script_version = script_resp.json()["script"]["version"]

        scenes_data: list[dict] = []
        for idx, spec in enumerate(DOCUMENTARY_SCENES_25):
            if idx < 20:
                edit_resp = client.post(
                    f"/studio/videos/{video_id}/script/scenes/{idx}",
                    headers={"Idempotency-Key": f"rec04-doc-init-scene-{idx}"},
                    json={
                        "expected_version": script_version,
                        "narration": spec["narration"],
                        "caption": spec["caption"],
                        "image_prompt": spec["image_prompt"],
                        "claim_ids": [],
                    },
                )
            else:
                edit_resp = client.post(
                    f"/studio/videos/{video_id}/script/scenes",
                    headers={"Idempotency-Key": f"rec04-doc-add-scene-{idx}"},
                    json={
                        "expected_version": script_version,
                        "position": idx,
                        "narration": spec["narration"],
                        "caption": spec["caption"],
                        "image_prompt": spec["image_prompt"],
                        "claim_ids": [],
                    },
                )
            assert edit_resp.status_code == 200, edit_resp.text
            script_version = edit_resp.json()["script"]["version"]
            scenes_data = edit_resp.json()["scenes"]

        assert len(scenes_data) == 25
        scene_ids = [s["id"] for s in scenes_data]
        stage_timings["setup_and_script_s"] = round(time.monotonic() - t0, 3)

        # 3. Importação de mídias reais (PNGs 1080p, MP4s 1080p, PNG overlays, MP4 PiP) + cenas geradas localmente
        t0 = time.monotonic()
        provenance_records: list[dict[str, str]] = []

        palettes = [
            ((18, 26, 46), (48, 72, 118), (245, 184, 46), "circles"),
            ((16, 36, 43), (44, 92, 104), (80, 220, 200), "bars"),
            ((24, 34, 54), (56, 84, 128), (255, 196, 64), "waves"),
            ((18, 42, 36), (44, 100, 84), (110, 240, 170), "network"),
            ((34, 24, 48), (82, 58, 114), (240, 160, 255), "circuit"),
        ]

        # Gerar e importar overlays (PNG badge cena 0, MP4 PiP cena 1, PNG badge cena 12)
        overlay_badge_png = make_rich_png((640, 360), (245, 184, 46), (255, 250, 230), (24, 32, 56), shape="badge")
        overlay_mid_png = make_rich_png((640, 360), (40, 160, 210), (235, 248, 255), (16, 32, 48), shape="badge")
        overlay_pip_mp4 = make_real_mp4(fixtures_dir / "overlay_pip.mp4", width=640, height=360, duration_s=5.0, kind="pip")

        # MP4s base em movimento contínuo (cenas 2, 10 e 18 -> exercitam PRE-1 sem duplicação de legenda)
        mp4_base_scenes = {
            2: make_real_mp4(fixtures_dir / "scene02_base.mp4", width=1920, height=1080, duration_s=22.0, kind="base", hue_speed=40),
            10: make_real_mp4(fixtures_dir / "scene10_base.mp4", width=1920, height=1080, duration_s=22.0, kind="mandelbrot", hue_speed=55),
            18: make_real_mp4(fixtures_dir / "scene18_base.mp4", width=1920, height=1080, duration_s=22.0, kind="base", hue_speed=70),
        }

        def _import_media(scene_idx: int, filename: str, payload: bytes, mime: str, expected_id: str | None = None) -> str:
            data = {"license": "CC0-1.0", "attribution": f"Estúdio REC-04.02 Cena {scene_idx:02d}"}
            if expected_id is not None:
                data["expected_asset_id"] = expected_id
            resp = client.post(
                f"/studio/videos/{video_id}/scenes/{scene_ids[scene_idx]}/media/import",
                data=data,
                files={"file": (filename, payload, mime)},
            )
            assert resp.status_code == 200, resp.text
            asset_id = resp.json()["asset"]["id"]
            provenance_records.append({
                "scene_idx": str(scene_idx),
                "asset_id": asset_id,
                "filename": filename,
                "mime": mime,
                "license": "CC0-1.0",
                "attribution": data["attribution"],
            })
            return asset_id

        # Cena 0: overlay PNG direita (pos=1) + base PNG
        badge0_id = _import_media(0, "overlay_badge_0.png", overlay_badge_png, "image/png")
        bg, grid, acc, shp = palettes[0]
        _import_media(0, "scene00_base.png", make_rich_png((1920, 1080), bg, grid, acc, shape=shp), "image/png", expected_id=badge0_id)
        ov0 = client.post(
            f"/studio/videos/{video_id}/scenes/{scene_ids[0]}/assets",
            json={"asset_id": badge0_id, "position": 1, "start_s": 0.6, "end_s": 2.8, "role": "overlay"},
        )
        assert ov0.status_code == 201, ov0.text

        # Cena 1: PiP MP4 esquerda (pos=2 -> P2-1 y=0.50 sem colidir HUD) + base PNG
        pip1_id = _import_media(1, "overlay_pip_1.mp4", overlay_pip_mp4, "video/mp4")
        bg, grid, acc, shp = palettes[1]
        _import_media(1, "scene01_base.png", make_rich_png((1920, 1080), bg, grid, acc, shape=shp), "image/png", expected_id=pip1_id)
        ov1 = client.post(
            f"/studio/videos/{video_id}/scenes/{scene_ids[1]}/assets",
            json={"asset_id": pip1_id, "position": 2, "start_s": 0.6, "end_s": 2.8, "role": "overlay"},
        )
        assert ov1.status_code == 201, ov1.text

        # Cena 12: overlay PNG direita (pos=1) + base PNG
        badge12_id = _import_media(12, "overlay_badge_12.png", overlay_mid_png, "image/png")
        bg, grid, acc, shp = palettes[2]
        _import_media(12, "scene12_base.png", make_rich_png((1920, 1080), bg, grid, acc, shape=shp), "image/png", expected_id=badge12_id)
        ov12 = client.post(
            f"/studio/videos/{video_id}/scenes/{scene_ids[12]}/assets",
            json={"asset_id": badge12_id, "position": 1, "start_s": 0.6, "end_s": 2.8, "role": "overlay"},
        )
        assert ov12.status_code == 201, ov12.text

        # Cenas 2..19 restantes: importar MP4 base (2, 10, 18) e PNGs 1080p nas demais; cenas 20..24 ficam para AssetsHandler
        for idx in range(2, 20):
            if idx == 12:
                continue
            if idx in mp4_base_scenes:
                _import_media(idx, f"scene{idx:02d}_base.mp4", mp4_base_scenes[idx], "video/mp4")
            else:
                bg, grid, acc, shp = palettes[idx % len(palettes)]
                _import_media(idx, f"scene{idx:02d}_base.png", make_rich_png((1920, 1080), bg, grid, acc, shape=shp), "image/png")

        stage_timings["media_import_and_overlays_s"] = round(time.monotonic() - t0, 3)

        # 4. Run #1 via ProductionCoordinator (rota HTTP real /production-runs)
        t_run1 = time.monotonic()
        run1_resp = client.post(
            f"/studio/videos/{video_id}/production-runs",
            headers={"Idempotency-Key": "rec04-doc-run-1"},
            json={"stages": ["script", "factcheck", "storyboard", "assets", "render", "qa", "approval"]},
        )
        run1_wall_s = time.monotonic() - t_run1
        assert run1_resp.status_code == 202, run1_resp.text
        run1_id = run1_resp.json()["run_id"]
        stage_timings["run1_production_coordinator_s"] = round(run1_wall_s, 3)

        run1_data = client.get(f"/studio/videos/{video_id}/production-runs/{run1_id}").json()
        run1_states = {st["stage"]: st["state"] for st in run1_data["stages"]}
        for st_name in ("script", "factcheck", "storyboard", "assets", "render", "qa"):
            if run1_states.get(st_name) != "SUCCEEDED":
                with conn.cursor() as cur:
                    cur.execute("SELECT status, error FROM studio.render_jobs WHERE video_id = %s ORDER BY created_at DESC LIMIT 3", (video_id,))
                    rjobs = cur.fetchall()
                pytest.fail(f"Run #1 stage {st_name} failed: render_jobs={rjobs} run={run1_data}")
        assert run1_data["state"] == "WAITING_HUMAN"

        # Snapshot do cache do RenderPlan no Postgres antes da edição seletiva
        plan_repo = PostgresRenderPlanRepository(lambda: psycopg.connect(dsn))
        plan_id = f"plan:{video_id}"
        plan_v1 = plan_repo.latest_plan(plan_id)
        assert plan_v1 is not None and plan_v1.revision == 1
        entries_v1 = plan_repo.entries(plan_id)

        shot_ids_by_scene_v1: dict[str, list[str]] = {
            sc.scene_id: [sh.shot_id for sh in sc.base_shots]
            for sc in plan_v1.timeline.scenes
        }
        v1_visual_meta: dict[str, tuple[str, str, str, int]] = {}
        for sid, sh_ids in shot_ids_by_scene_v1.items():
            for sh_id in sh_ids:
                ent = entries_v1[NodeId("visual", sh_id)]
                v1_visual_meta[sh_id] = (
                    ent.fingerprint,
                    ent.artifact_sha256,
                    ent.artifact_uri,
                    Path(ent.artifact_uri).stat().st_mtime_ns,
                )
        v1_narration_meta: dict[str, tuple[str, str, str, int]] = {}
        for sid in scene_ids:
            ent = entries_v1[NodeId("narration", sid)]
            v1_narration_meta[sid] = (
                ent.fingerprint,
                ent.artifact_sha256,
                ent.artifact_uri,
                Path(ent.artifact_uri).stat().st_mtime_ns,
            )

        # 5. Edição humana simulada na Cena 15 + Regeneração Seletiva Run #2
        t0 = time.monotonic()
        tr_resp = client.post(
            f"/studio/videos/{video_id}/transition",
            json={"expected": "AWAITING_APPROVAL", "new": "SCRIPTED"},
        )
        assert tr_resp.status_code == 200, tr_resp.text

        edit15_resp = client.post(
            f"/studio/videos/{video_id}/script/scenes/15",
            headers={"Idempotency-Key": "rec04-doc-edit-scene-15"},
            json={
                "expected_version": script_version,
                "narration": SCENE_15_V2["narration"],
                "caption": SCENE_15_V2["caption"],
                "image_prompt": SCENE_15_V2["image_prompt"],
                "claim_ids": [],
            },
        )
        assert edit15_resp.status_code == 200, edit15_resp.text
        scenes_v2 = edit15_resp.json()["scenes"]
        assert [s["id"] for s in scenes_v2] == scene_ids

        scene15_png_v2 = make_rich_png((1920, 1080), (43, 22, 42), (112, 60, 102), (255, 200, 70), shape="circuit")
        _import_media(15, "scene15_v2.png", scene15_png_v2, "image/png")
        stage_timings["edit_scene15_s"] = round(time.monotonic() - t0, 3)

        t_run2 = time.monotonic()
        run2_resp = client.post(
            f"/studio/videos/{video_id}/production-runs",
            headers={"Idempotency-Key": "rec04-doc-run-2"},
            json={"stages": ["script", "factcheck", "storyboard", "assets", "render", "qa", "approval"]},
        )
        run2_wall_s = time.monotonic() - t_run2
        assert run2_resp.status_code == 202, run2_resp.text
        run2_id = run2_resp.json()["run_id"]
        stage_timings["run2_selective_regen_s"] = round(run2_wall_s, 3)

        run2_data = client.get(f"/studio/videos/{video_id}/production-runs/{run2_id}").json()
        run2_states = {st["stage"]: st["state"] for st in run2_data["stages"]}
        for st_name in ("script", "factcheck", "storyboard", "assets", "render", "qa"):
            assert run2_states.get(st_name) == "SUCCEEDED", f"Run #2 stage {st_name} failed: {run2_data}"
        assert run2_data["state"] == "WAITING_HUMAN"

        # Verificar preservação de cache para TODAS as 24 cenas intocadas
        plan_v2 = plan_repo.latest_plan(plan_id)
        assert plan_v2 is not None and plan_v2.revision == 2
        entries_v2 = plan_repo.entries(plan_id)

        untouched_scene_ids = [sid for idx, sid in enumerate(scene_ids) if idx != 15]
        assert len(untouched_scene_ids) == 24
        reused_narration_nodes = 0
        reused_visual_nodes = 0
        for sid in untouched_scene_ids:
            e2_nar = entries_v2[NodeId("narration", sid)]
            nar_v2_tuple = (
                e2_nar.fingerprint,
                e2_nar.artifact_sha256,
                e2_nar.artifact_uri,
                Path(e2_nar.artifact_uri).stat().st_mtime_ns,
            )
            assert nar_v2_tuple == v1_narration_meta[sid], f"Narração intocada {sid} não reusou cache"
            reused_narration_nodes += 1
            for sh_id in shot_ids_by_scene_v1[sid]:
                e2_vis = entries_v2[NodeId("visual", sh_id)]
                vis_v2_tuple = (
                    e2_vis.fingerprint,
                    e2_vis.artifact_sha256,
                    e2_vis.artifact_uri,
                    Path(e2_vis.artifact_uri).stat().st_mtime_ns,
                )
                assert vis_v2_tuple == v1_visual_meta[sh_id], f"Shot visual intocado {sh_id} não reusou cache"
                reused_visual_nodes += 1

        # Cena 15 editada deve ter novos hashes
        e2_s15_nar = entries_v2[NodeId("narration", scene_ids[15])]
        assert e2_s15_nar.fingerprint != v1_narration_meta[scene_ids[15]][0]
        assert e2_s15_nar.artifact_sha256 != v1_narration_meta[scene_ids[15]][1]
        s15_shots_v2 = [sh.shot_id for sc in plan_v2.timeline.scenes if sc.scene_id == scene_ids[15] for sh in sc.base_shots]
        assert any(
            entries_v2[NodeId("visual", sh_id)].artifact_sha256 != v1_visual_meta.get(sh_id, ("", "", "", 0))[1]
            for sh_id in s15_shots_v2
        )

        # 6. Legendas via HTTP + V2-F7 Thumbnail Check (rota HTTP + 3 opções VideoPackaging)
        t0 = time.monotonic()
        srt_final = client.get(f"/studio/videos/{video_id}/subtitles")
        vtt_final = client.get(f"/studio/videos/{video_id}/subtitles.vtt")
        ass_final = client.get(f"/studio/videos/{video_id}/subtitles.ass")
        assert srt_final.status_code == 200 and "microprocessadores" in srt_final.text.lower()
        assert vtt_final.status_code == 200 and vtt_final.text.startswith("WEBVTT")
        assert ass_final.status_code == 200 and "[Script Info]" in ass_final.text and "Dialogue:" in ass_final.text

        # V2-F7 Thumbnail HTTP (Cena 0 -> PillowThumbnail 1280x720 JPEG <= 2MB)
        thumb_resp = client.get(f"/studio/videos/{video_id}/thumbnail")
        assert thumb_resp.status_code == 200, thumb_resp.text
        assert thumb_resp.headers["content-type"].startswith("image/jpeg")
        assert len(thumb_resp.content) <= 2 * 1024 * 1024
        with Image.open(io.BytesIO(thumb_resp.content)) as t_img:
            assert t_img.size == (1280, 720)

        # V2-F7 3 opções distintas de thumbnail/título (VideoPackaging + PillowThumbnail)
        packaging = VideoPackaging(
            title="A História da Computação: Da Mecânica aos Cérebros de Silício",
            title_claim=TitleClaim(kind="verifiable_promise", statement="Marcos históricos verificados da computação"),
            description="Documentário cronológico em 25 capítulos sobre a evolução da computação.",
            tags=("historia da computacao", "alan turing", "silicio"),
            chapters=(
                Chapter(start_seconds=0, title="Ato I: Instrumentos Mecânicos"),
                Chapter(start_seconds=120, title="Ato II: Lógica, Válvulas e Silício"),
                Chapter(start_seconds=240, title="Ato III: Redes, Nuvem e IA"),
            ),
            sources=(SourceCitation(name="Wikipedia — História da Computação", url=SOURCE_URL),),
            cta="Inscreva-se para mais documentários históricos.",
            variants=(
                PackagingVariant(
                    variant_id="thumb-opt-1",
                    title="Do Ábaco à IA: A Jornada Completa da Computação",
                    thumbnail_concept="Ábaco antigo e engrenagens mecânicas com contraste dourado",
                    rationale="Apelo histórico clássico focado na origem mecânica",
                    title_claim=TitleClaim(kind="verifiable_promise", statement="Cobre do ábaco à IA"),
                ),
                PackagingVariant(
                    variant_id="thumb-opt-2",
                    title="Como Turing e o Silício Mudaram o Mundo Moderno",
                    thumbnail_concept="Máquina Universal de Turing e circuitos de silício iluminados",
                    rationale="Foco no ponto de inflexão teórico e eletrônico",
                    title_claim=TitleClaim(kind="verifiable_promise", statement="Explora Turing e semicondutores"),
                ),
                PackagingVariant(
                    variant_id="thumb-opt-3",
                    title="25 Marcos da Computação em 6 Minutos",
                    thumbnail_concept="Rede neural profunda em perspectiva com grade luminosa",
                    rationale="Ênfase em síntese cronológica direta e moderna",
                    title_claim=TitleClaim(kind="verifiable_promise", statement="25 marcos cronológicos"),
                ),
            ),
        )
        assert len(packaging.variants) == 3 and packaging.limit_violations() == ()

        thumb_maker = PillowThumbnail()
        thumb_options_info: list[dict] = []
        for opt_idx, scene_idx_for_thumb in enumerate((0, 9, 24), start=1):
            bg, grid, acc, shp = palettes[scene_idx_for_thumb % len(palettes)]
            src_png = fixtures_dir / f"thumb_src_{opt_idx}.png"
            src_png.write_bytes(make_rich_png((1920, 1080), bg, grid, acc, shape=shp))
            jpg_bytes = thumb_maker.make(src_png)
            assert len(jpg_bytes) <= 2 * 1024 * 1024
            with Image.open(io.BytesIO(jpg_bytes)) as opt_img:
                assert opt_img.size == (1280, 720)
            thumb_options_info.append({
                "variant_id": packaging.variants[opt_idx - 1].variant_id,
                "title": packaging.variants[opt_idx - 1].title,
                "concept": packaging.variants[opt_idx - 1].thumbnail_concept,
                "source_scene_idx": scene_idx_for_thumb,
                "bytes": len(jpg_bytes),
                "width": 1280,
                "height": 720,
                "_bytes": jpg_bytes,
            })
        stage_timings["subtitles_and_thumbnails_s"] = round(time.monotonic() - t0, 3)

        # 7. QA persistido no Postgres + Ledger $0.00 + Kill Switch BLOCKED
        v_repo = PostgresVideoRepository(lambda: psycopg.connect(dsn))
        video_entity = v_repo.get_video(video_id)
        assert video_entity is not None
        assert video_entity.status.value == "AWAITING_APPROVAL"
        qa_report = video_entity.qa_report
        assert qa_report is not None
        assert qa_report.coverage.status == "verified"
        assert len(qa_report.blocking_findings) == 0
        assert qa_report.is_publishable is True
        assert CHECK_OVERLAY in qa_report.checks_run
        assert CHECK_CAPTION_SYNC in qa_report.checks_run

        u_repo = PostgresUsageRepository(lambda: psycopg.connect(dsn))
        assert u_repo.spent_video(video_id) == 0.0
        cost_resp = client.get(f"/studio/videos/{video_id}/cost-breakdown")
        assert cost_resp.status_code == 200 and cost_resp.json()["total_usd"] == 0.0

        pub_resp = client.post(f"/studio/videos/{video_id}/publication/publish")
        assert pub_resp.status_code == 200
        pub_data = pub_resp.json()
        assert pub_data["result"] == "BLOCKED"
        assert pub_data.get("youtube_video_id") is None
        assert "disabled by configuration" in (pub_data.get("detail") or "")
        assert client.get(f"/studio/videos/{video_id}").json()["status"] == "AWAITING_APPROVAL"

        # 8. Baixar MP4 final e medir ffprobe, ebur128, drift, frames e conteúdo físico
        t0 = time.monotonic()
        file_resp = client.get(f"/studio/videos/{video_id}/file")
        assert file_resp.status_code == 200
        final_mp4 = tmp_path / "rec04_02_documentary.mp4"
        final_mp4.write_bytes(file_resp.content)
        mp4_sha256 = sha256_file(final_mp4)
        mp4_bytes = final_mp4.stat().st_size
        assert mp4_bytes > 5_000_000

        probe_data = probe_full(final_mp4)
        qa_metrics = FfmpegQa().analyze(final_mp4)
        duration_s = float(qa_metrics["duration_s"])
        assert 300.0 <= duration_s <= 480.0, f"Duração fora da janela 300–480s: {duration_s:.3f}s"
        assert qa_metrics["width"] == 1920 and qa_metrics["height"] == 1080
        assert qa_metrics["has_audio"] is True
        assert qa_metrics["video_codec"] in ("h264", "avc1")
        assert qa_metrics["audio_codec"] == "aac"
        assert qa_metrics["integrated_lufs"] is not None and -20.0 <= qa_metrics["integrated_lufs"] <= -12.0
        assert qa_metrics["true_peak_dbtp"] is not None and qa_metrics["true_peak_dbtp"] <= -1.0
        assert qa_metrics["black_ratio"] < 0.05
        assert qa_metrics["frozen_ratio"] < 0.25
        assert qa_metrics["silence_ratio"] < 0.25

        # Verificar WAVs de narração e calcular inícios de cena
        narration_durations: list[float] = []
        total_wav_rms: list[float] = []
        for idx, sid in enumerate(scene_ids):
            wav_resp = client.get(f"/studio/videos/{video_id}/scenes/{sid}/narration.wav")
            assert wav_resp.status_code == 200
            dur, rms, peak = wav_rms_and_duration(wav_resp.content)
            assert dur >= 6.0 and rms > 200.0 and peak > 1000
            narration_durations.append(dur)
            total_wav_rms.append(rms)

        scene_starts: list[float] = []
        cursor = 0.0
        for sc_plan in plan_v2.timeline.scenes:
            scene_starts.append(cursor)
            cursor += sum(sh.duration_ticks for sh in sc_plan.base_shots) / (plan_v2.timeline.ticks_per_second or 1000)

        last_narration_end_s = scene_starts[-1] + narration_durations[-1]
        audio_stream = next(s for s in probe_data["streams"] if s["codec_type"] == "audio")
        mp4_audio_dur_s = float(audio_stream.get("duration") or duration_s)
        caption_drift = compute_audio_caption_drift(
            plan_v2,
            mp4_audio_duration_s=mp4_audio_dur_s,
            last_narration_end_s=last_narration_end_s,
        )
        assert abs(caption_drift["drift_vs_last_narration_end_ms"]) <= 500

        # Verificar PiP/overlays e ausência de colisão com HUD (P2-1) + movimento em MP4s base
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        f_s0_before = extract_frame(final_mp4, scene_starts[0] + 0.25, frames_dir / "s0_before.png")
        f_s0_overlay = extract_frame(final_mp4, scene_starts[0] + 1.60, frames_dir / "s0_overlay.png")
        f_s0_after = extract_frame(final_mp4, scene_starts[0] + 3.20, frames_dir / "s0_after.png")
        diff_png_ov_in = mean_abs_diff(f_s0_before, f_s0_overlay, box=(990, 160, 1860, 660))
        diff_png_ov_out = mean_abs_diff(f_s0_overlay, f_s0_after, box=(990, 160, 1860, 660))
        assert diff_png_ov_in > 12.0 and diff_png_ov_out > 12.0

        f_s1_before = extract_frame(final_mp4, scene_starts[1] + 0.25, frames_dir / "s1_before.png")
        f_s1_pip_a = extract_frame(final_mp4, scene_starts[1] + 1.10, frames_dir / "s1_pip_a.png")
        f_s1_pip_b = extract_frame(final_mp4, scene_starts[1] + 2.10, frames_dir / "s1_pip_b.png")
        f_s1_after = extract_frame(final_mp4, scene_starts[1] + 3.20, frames_dir / "s1_after.png")
        diff_pip_in = mean_abs_diff(f_s1_before, f_s1_pip_a, box=(60, 290, 930, 790))
        diff_pip_motion = mean_abs_diff(f_s1_pip_a, f_s1_pip_b, box=(60, 290, 930, 790))
        diff_pip_out = mean_abs_diff(f_s1_pip_b, f_s1_after, box=(60, 290, 930, 790))
        diff_hud_pip = mean_abs_diff(f_s1_before, f_s1_pip_a, box=(50, 90, 560, 250))
        assert diff_pip_in > 12.0 and diff_pip_motion > 10.0 and diff_pip_out > 12.0
        assert diff_hud_pip < 5.0, f"P2-1 violado: PiP alterou zona HUD superior esquerdo (diff={diff_hud_pip:.2f})"

        f_s2_a = extract_frame(final_mp4, scene_starts[2] + 2.0, frames_dir / "s2_mp4_a.png")
        f_s2_b = extract_frame(final_mp4, scene_starts[2] + 4.2, frames_dir / "s2_mp4_b.png")
        diff_s2_mp4 = mean_abs_diff(f_s2_a, f_s2_b)
        assert diff_s2_mp4 > 15.0

        f_s12_ov = extract_frame(final_mp4, scene_starts[12] + 1.8, frames_dir / "s12_overlay.png")
        f_s15_v2 = extract_frame(final_mp4, scene_starts[15] + 2.5, frames_dir / "s15_edited_v2.png")
        f_s18_mp4 = extract_frame(final_mp4, scene_starts[18] + 2.5, frames_dir / "s18_imported_mp4.png")
        f_s21_gen = extract_frame(final_mp4, scene_starts[21] + 2.5, frames_dir / "s21_studio_generated.png")
        f_s24_end = extract_frame(final_mp4, scene_starts[24] + 2.5, frames_dir / "s24_end_doc.png")

        sampled_frames = [
            ("scene00_png_overlay", scene_starts[0] + 1.80, f_s0_overlay, "Cena 0 com overlay PNG gráfico à direita"),
            ("scene01_mp4_pip", scene_starts[1] + 1.20, f_s1_pip_a, "Cena 1 com PiP MP4 à esquerda (sem colisão HUD)"),
            ("scene02_imported_mp4", scene_starts[2] + 2.00, f_s2_a, "Cena 2 com MP4 base importado e ASS único (PRE-1)"),
            ("scene12_mid_overlay", scene_starts[12] + 1.80, f_s12_ov, "Cena 12 meio do documentário com overlay PNG"),
            ("scene15_edited_v2", scene_starts[15] + 2.50, f_s15_v2, "Cena 15 após edição e regeneração seletiva"),
            ("scene18_imported_mp4", scene_starts[18] + 2.50, f_s18_mp4, "Cena 18 com B-roll MP4 importado"),
            ("scene21_studio_generated", scene_starts[21] + 2.50, f_s21_gen, "Cena 21 gerada localmente pelo AssetsHandler"),
            ("scene24_end_doc", scene_starts[24] + 2.50, f_s24_end, "Cena 24 encerramento do documentário"),
        ]
        for label, _, img, _ in sampled_frames:
            st = image_stats(img)
            assert st["std_luma"] > 8.0, f"Frame {label} quase uniforme: {st}"

        speech_rms = audio_window_rms(final_mp4, scene_starts[0] + 1.0, 4.0, tmp_path / "speech_win.wav")
        assert speech_rms > 300.0
        stage_timings["content_verification_s"] = round(time.monotonic() - t0, 3)
        stage_timings["total_wall_s"] = round(time.monotonic() - t_suite_start, 3)

        # Uso de recursos (processo pai + filhos via getrusage)
        ru_self = resource.getrusage(resource.RUSAGE_SELF)
        ru_child = resource.getrusage(resource.RUSAGE_CHILDREN)
        self_rss_mb = round(ru_self.ru_maxrss / 1024.0, 2)
        children_rss_mb = round(ru_child.ru_maxrss / 1024.0, 2)
        time_saved_s = round(run1_wall_s - run2_wall_s, 3)
        time_saved_pct = round((time_saved_s / run1_wall_s) * 100.0, 2) if run1_wall_s > 0 else 0.0

        # 9. Gravar artefatos e manifesto no diretório exclusivo quando REC04_DOC_OUT_DIR estiver definido
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_frames = out_dir / "frames"
            out_frames.mkdir(parents=True, exist_ok=True)
            out_subs = out_dir / "subtitles"
            out_subs.mkdir(parents=True, exist_ok=True)
            out_thumbs = out_dir / "thumbnails"
            out_thumbs.mkdir(parents=True, exist_ok=True)

            shutil.copy2(final_mp4, out_dir / "rec04_02_documentary.mp4")
            (out_subs / "documentary.srt").write_text(srt_final.text, encoding="utf-8")
            (out_subs / "documentary.vtt").write_text(vtt_final.text, encoding="utf-8")
            (out_subs / "documentary.ass").write_text(ass_final.text, encoding="utf-8")

            primary_thumb_path = out_thumbs / "thumbnail_http_primary.jpg"
            primary_thumb_path.write_bytes(thumb_resp.content)
            for idx, opt in enumerate(thumb_options_info, start=1):
                opt_path = out_thumbs / f"thumbnail_option_{idx}.jpg"
                raw = opt.pop("_bytes")
                opt_path.write_bytes(raw)
                opt["file"] = f"thumbnails/thumbnail_option_{idx}.jpg"
                opt["sha256"] = sha256_file(opt_path)

            manifest_frames = []
            for label, ts, img, desc in sampled_frames:
                dst = out_frames / f"{label}.png"
                img.save(dst)
                manifest_frames.append({
                    "label": label,
                    "timestamp_s": round(ts, 3),
                    "description": desc,
                    "file": f"frames/{label}.png",
                    "bytes": dst.stat().st_size,
                    "sha256": sha256_file(dst),
                    "stats": image_stats(img),
                })

            video_stream = next(s for s in probe_data["streams"] if s["codec_type"] == "video")
            baseline = _baseline_v4_00_reference()

            manifest = {
                "schema_version": "rec04-02-manifest/1",
                "task_id": "REC-04.02",
                "requirement_id": "R11",
                "run_id": run_label,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "git": git_info(),
                "versions": {
                    "ffmpeg": tool_version(["ffmpeg", "-version"]),
                    "ffprobe": tool_version(["ffprobe", "-version"]),
                    "piper": piper_version(),
                    "piper_voice_model": "/opt/voices/pt_BR-faber-medium.onnx",
                },
                "profiles": {
                    "economic_local": {
                        "status": "EXECUTED",
                        "providers": {"text": "demo:v4", "image": "placeholder:v4", "voice": "piper:pt_BR-faber-medium", "renderer": "ffmpeg"},
                        "cost_usd": 0.0,
                    },
                    "balanced_local": {
                        "status": "DEFERRED",
                        "reason": "BLOCKED_LOCAL_PAID_DEPENDENCY: sem APIs pagas nem GPU local no container; orçamento travado em $0.00.",
                        "cost_usd": 0.0,
                    },
                    "premium": {
                        "status": "OUT_OF_SCOPE",
                        "reason": "Requer autorização explícita do operador e orçamento pago.",
                    },
                },
                "governance": {
                    "studio_publication_enabled": False,
                    "kill_switch_result": pub_data["result"],
                    "kill_switch_detail": pub_data.get("detail"),
                    "youtube_video_id": pub_data.get("youtube_video_id"),
                    "budget_guard_enabled": True,
                    "max_cost_usd_per_video": 0.0,
                    "max_cost_usd_per_month": 0.0,
                    "observed_api_cost_usd": 0.0,
                    "video_final_status": "AWAITING_APPROVAL",
                    "human_review_status": "AWAITING_HUMAN_REVIEW",
                    "auto_approved_in_test": False,
                },
                "documentary_structure": {
                    "topic": "A História da Computação: Da Mecânica aos Cérebros de Silício",
                    "scenes_count": 25,
                    "imported_png_base_scenes": 17,
                    "imported_mp4_base_scenes": 3,
                    "local_generated_base_scenes": 5,
                    "overlays_count": 3,
                    "rebaseline_note": (
                        "Rebaseline controlado vs V4-00 (18 cenas / 345.80s): expandido para 25 cenas "
                        "na mesma linha cronológica da História da Computação para cumprir SESSION-HANDOFF §5 (>=25 cenas)."
                    ),
                },
                "artifact": {
                    "mp4_relative_path": f"storage/output/runs/{run_label}/rec04_02_documentary.mp4",
                    "mp4_sha256": mp4_sha256,
                    "mp4_bytes": mp4_bytes,
                    "subtitles": {
                        "srt_sha256": sha256_file(out_subs / "documentary.srt"),
                        "vtt_sha256": sha256_file(out_subs / "documentary.vtt"),
                        "ass_sha256": sha256_file(out_subs / "documentary.ass"),
                        "plan_subtitle_cues": len(plan_v2.timeline.subtitles),
                    },
                },
                "thumbnails_v2_f7": {
                    "http_endpoint": f"/studio/videos/{video_id}/thumbnail",
                    "http_primary_file": "thumbnails/thumbnail_http_primary.jpg",
                    "http_primary_sha256": sha256_file(primary_thumb_path),
                    "http_primary_bytes": primary_thumb_path.stat().st_size,
                    "packaging_variants_count": len(packaging.variants),
                    "packaging_options": thumb_options_info,
                    "note": "GET /thumbnail usa PillowThumbnail em produção; VideoPackaging valida 3 conceitos no domínio.",
                },
                "ffprobe": {
                    "duration_s": duration_s,
                    "bit_rate_bps": int(probe_data["format"].get("bit_rate") or 0),
                    "video": {
                        "codec_name": video_stream.get("codec_name"),
                        "width": int(video_stream.get("width") or 0),
                        "height": int(video_stream.get("height") or 0),
                        "r_frame_rate": video_stream.get("r_frame_rate"),
                        "nb_frames": int(video_stream.get("nb_frames") or 0),
                        "pix_fmt": video_stream.get("pix_fmt"),
                    },
                    "audio": {
                        "codec_name": audio_stream.get("codec_name"),
                        "sample_rate": int(audio_stream.get("sample_rate") or 0),
                        "channels": int(audio_stream.get("channels") or 0),
                        "bit_rate_bps": int(audio_stream.get("bit_rate") or 0),
                    },
                },
                "qa_measured": {
                    "ffmpeg_qa": qa_metrics,
                    "caption_sync_drift": caption_drift,
                    "studio_qa_report": {
                        "coverage_status": qa_report.coverage.status,
                        "is_publishable": qa_report.is_publishable,
                        "checks_run": list(qa_report.checks_run),
                        "blocking_findings_count": len(qa_report.blocking_findings),
                    },
                    "content_pixel_checks": {
                        "scene0_png_overlay_enter_diff": round(diff_png_ov_in, 2),
                        "scene0_png_overlay_exit_diff": round(diff_png_ov_out, 2),
                        "scene1_mp4_pip_enter_diff": round(diff_pip_in, 2),
                        "scene1_mp4_pip_motion_diff": round(diff_pip_motion, 2),
                        "scene1_mp4_pip_exit_diff": round(diff_pip_out, 2),
                        "scene1_hud_top_left_during_pip_diff": round(diff_hud_pip, 2),
                        "scene2_imported_mp4_motion_diff": round(diff_s2_mp4, 2),
                    },
                    "audio_dynamics": {
                        "speech_window_rms_pcm16": round(speech_rms, 1),
                        "mean_scene_narration_rms_pcm16": round(sum(total_wav_rms) / len(total_wav_rms), 1),
                        "min_scene_narration_duration_s": round(min(narration_durations), 3),
                        "max_scene_narration_duration_s": round(max(narration_durations), 3),
                    },
                },
                "selective_regeneration": {
                    "plan_revision_before": 1,
                    "plan_revision_after": 2,
                    "edited_scene_idx": 15,
                    "edited_scene_id": scene_ids[15],
                    "untouched_scenes_count": 24,
                    "reused_narration_nodes": reused_narration_nodes,
                    "reused_visual_nodes": reused_visual_nodes,
                    "run1_wall_s": round(run1_wall_s, 3),
                    "run2_wall_s": round(run2_wall_s, 3),
                    "time_saved_s": time_saved_s,
                    "time_saved_pct": time_saved_pct,
                },
                "stage_timings_s": stage_timings,
                "resource_usage": {
                    "cpu_user_seconds": round(ru_self.ru_utime + ru_child.ru_utime, 3),
                    "cpu_system_seconds": round(ru_self.ru_stime + ru_child.ru_stime, 3),
                    "cpu_total_seconds": round(ru_self.ru_utime + ru_child.ru_utime + ru_self.ru_stime + ru_child.ru_stime, 3),
                    "peak_rss_self_mb": self_rss_mb,
                    "peak_rss_children_mb": children_rss_mb,
                    "rss_sum_upper_bound_mb": round(self_rss_mb + children_rss_mb, 2),
                    "memory_limitation_note": (
                        "Linux getrusage reporta ru_maxrss independente do processo pai (RUSAGE_SELF) e do maior filho "
                        "terminado (RUSAGE_CHILDREN); rss_sum_upper_bound_mb é o limite superior teórico."
                    ),
                },
                "provenance_and_licenses": provenance_records,
                "sampled_frames": manifest_frames,
                "v4_00_paired_comparison": {
                    "baseline_v4_00": baseline,
                    "rec04_02": {
                        "duration_s": duration_s,
                        "scenes_count": 25,
                        "integrated_lufs": qa_metrics["integrated_lufs"],
                        "true_peak_dbtp": qa_metrics["true_peak_dbtp"],
                        "frozen_ratio": qa_metrics["frozen_ratio"],
                        "silence_ratio": qa_metrics["silence_ratio"],
                        "black_ratio": qa_metrics["black_ratio"],
                        "run1_wall_s": round(run1_wall_s, 3),
                        "run2_selective_regen_wall_s": round(run2_wall_s, 3),
                        "cost_api_usd": 0.0,
                    },
                    "deltas": {
                        "duration_delta_s": round(duration_s - float(baseline["duration_s"]), 2),
                        "scenes_delta": 25 - int(baseline["scenes_count"]),
                        "frozen_ratio_delta": round(qa_metrics["frozen_ratio"] - float(baseline["frozen_ratio"]), 4),
                    },
                },
            }
            (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    finally:
        if hasattr(studio, "close"):
            studio.close()
