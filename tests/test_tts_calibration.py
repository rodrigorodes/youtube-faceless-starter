"""F4-03: estimativa de duração comparada com a voz real do produto, medida.

Não é um teste de fumaça: sintetiza o corpus inteiro com o **mesmo** Piper e a
**mesma** voz do renderer (``piper:pt_BR-faber-medium``) e compara com a
estimativa. Sem Piper, sem voz do produto ou com versão/hash diferentes, os
testes são **pulados com motivo** — a calibração não vale para outra voz.

Execução (imagem com piper-tts 1.8.0, a de testes ``yfs-test``; voz extraída da
imagem do renderer, que confere o sha256 no build):

    docker run --rm --network none -v "$PWD:/workspace" \
      -v /caminho/voices:/opt/voices:ro -w /workspace \
      -e PYTHONPATH=/workspace/renderer -e PIPER_VOICE=/opt/voices/pt_BR-faber-medium.onnx \
      --entrypoint python3 yfs-test:latest -m pytest -q -p no:cacheprovider tests/test_tts_calibration.py

Evidência bruta (3 execuções): ``.superpowers/sdd/2026-11-20-…/tts-calibracao-evidence-run{1,2,3}.json``.
"""
import hashlib
import importlib.metadata
import json
import os
import sys
import tempfile
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderer"))

from app.studio.domain.narration_duration import (  # noqa: E402
    MEASURED_EFFECTIVE_WORDS_PER_MINUTE,
    MEASURED_PAUSE_SECONDS,
    MEASURED_SPEECH_WORDS_PER_MINUTE,
    MEASURED_UTTERANCE_OVERHEAD_SECONDS,
    estimate_text_durations,
    estimate_voice_durations,
)
from app.studio.tts_calibration import MEASURED_PIPER_VERSION, MEASURED_VOICE  # noqa: E402

CORPUS = ROOT / "scripts" / "tts_calibration_samples.json"
EVIDENCE_RUNS = tuple(
    ROOT / ".superpowers" / "sdd" / "2026-11-20-faceless-studio-v2-plano-de-implementacao"
    / f"tts-calibracao-evidence-run{run}.json"
    for run in (1, 2, 3)
)

# Tolerâncias declaradas a partir da medição de 2026-11-20. São relógio de
# parede de voz sintetizada: curtíssimos textos pesam mais (silêncio de borda
# proporcionalmente grande) e a própria síntese varia até ~4% entre execuções,
# por isso a faixa folgada para eles.
TOLERANCE_MODEL_ALL = 0.25        # modelo medido (overhead + ritmo + pausas), qualquer amostra
TOLERANCE_MODEL_DENSE = 0.10      # amostras com textos de >= 20 palavras
TOLERANCE_PURE_TOTAL = 0.10       # hipótese calibrada (172 wpm) em prosa/longo
TOLERANCE_PURE_SCENE = 0.15       # por cena do roteiro longo
TOLERANCE_RUN_TO_RUN = 0.05       # mesma síntese, execuções diferentes
TOLERANCE_EVIDENCE = 0.01         # constantes x evidência gravada (ritmo efetivo/líquido)


def _load_corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _voice_or_skip():
    # Primeiro o arquivo (barato): importar `piper` carrega onnxruntime e custa
    # memória — não faz sentido pagar isso só para descobrir que a voz não está montada.
    voice_path = Path(os.environ.get("PIPER_VOICE", "/opt/voices/pt_BR-faber-medium.onnx"))
    if not voice_path.exists():
        pytest.skip(f"voz do produto ausente em {voice_path}; defina PIPER_VOICE ou monte /opt/voices")
    piper = pytest.importorskip(
        "piper", reason="piper-tts não instalado; calibração requer a imagem do renderer")
    try:
        version = importlib.metadata.version("piper-tts")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - distribuição exótica
        version = getattr(piper, "__version__", None)
    if version != MEASURED_PIPER_VERSION:
        pytest.skip(f"piper-tts {version!r} != {MEASURED_PIPER_VERSION} medido; calibração não se aplica")

    corpus = _load_corpus()
    expected_sha = corpus["model_sha256"]
    digest = hashlib.sha256(voice_path.read_bytes()).hexdigest()
    if digest != expected_sha:
        pytest.skip(f"sha256 {digest[:16]}… != voz do produto {expected_sha[:16]}…; não é a voz calibrada")
    return piper.PiperVoice.load(str(voice_path))


@pytest.fixture(scope="module")
def measured() -> dict:
    """Duração real de cada amostra, sintetizando cada texto como o renderer faz."""
    voice = _voice_or_skip()
    corpus = _load_corpus()
    with tempfile.TemporaryDirectory(prefix="tts-calib-") as tmp:
        totals: dict[str, float] = {}
        scenes: dict[str, list[float]] = {}
        for sample in corpus["samples"]:
            durations = []
            for idx, text in enumerate(sample["texts"]):
                out = Path(tmp) / f"{sample['id']}-{idx}.wav"
                with wave.open(str(out), "wb") as wav:
                    voice.synthesize_wav(text, wav)
                with wave.open(str(out), "rb") as wav:
                    durations.append(wav.getnframes() / wav.getframerate())
            totals[sample["id"]] = sum(durations)
            scenes[sample["id"]] = durations
    assert all(total > 0 for total in totals.values())
    return {"corpus": corpus, "totals": totals, "scenes": scenes}


def _sample(corpus: dict, sample_id: str) -> dict:
    return next(s for s in corpus["samples"] if s["id"] == sample_id)


def test_measured_model_matches_the_real_voice_within_declared_tolerance(measured):
    """O modelo com pausas medidas (estimate_voice_durations) x WAV real do Piper."""
    corpus = measured["corpus"]
    failures = []
    for sample in corpus["samples"]:
        model = estimate_voice_durations(sample["texts"]).total_seconds
        real = measured["totals"][sample["id"]]
        error = abs(model - real) / real
        dense = min(len(text.split()) for text in sample["texts"]) >= 20
        tolerance = TOLERANCE_MODEL_DENSE if dense else TOLERANCE_MODEL_ALL
        if error > tolerance:
            failures.append((sample["id"], round(model, 2), round(real, 2), round(error, 3), tolerance))
    assert not failures, failures


def test_calibrated_default_rate_matches_prose_and_the_480s_script(measured):
    """A hipótese calibrada (172 palavras/minuto efetivas) no que o produto planeja."""
    corpus = measured["corpus"]
    long_sample = _sample(corpus, "longo_480s")
    estimated = estimate_text_durations(long_sample["texts"], MEASURED_EFFECTIVE_WORDS_PER_MINUTE)
    real_total = measured["totals"]["longo_480s"]
    assert abs(estimated.total_seconds - real_total) / real_total <= TOLERANCE_PURE_TOTAL
    for estimate, real in zip(estimated.scene_seconds, measured["scenes"]["longo_480s"]):
        assert abs(estimate - real) / real <= TOLERANCE_PURE_SCENE

    for sample_id in ("prosa_pontuada", "numeros_siglas"):
        sample = _sample(corpus, sample_id)
        estimate = estimate_text_durations(sample["texts"], MEASURED_EFFECTIVE_WORDS_PER_MINUTE).total_seconds
        real = measured["totals"][sample_id]
        assert abs(estimate - real) / real <= TOLERANCE_PURE_TOTAL, sample_id


def test_punctuation_adds_the_measured_pause_time(measured):
    """Mesmas palavras, com e sem pontuação: a diferença é o custo real das pausas."""
    with_pauses = measured["totals"]["prosa_pontuada"]
    without = measured["totals"]["prosa_sem_pontuacao"]
    delta = with_pauses - without
    marks = 10  # vírgulas e pontos da prosa pontuada
    assert delta > 2.0
    assert delta == pytest.approx(marks * MEASURED_PAUSE_SECONDS, abs=1.0)


def test_numbers_and_acronyms_stay_within_the_declared_tolerance(measured):
    """Números, moeda, porcentagem e siglas expandem de forma diferente da contagem de palavras."""
    sample = _sample(measured["corpus"], "numeros_siglas")
    model = estimate_voice_durations(sample["texts"]).total_seconds
    real = measured["totals"]["numeros_siglas"]
    assert abs(model - real) / real <= TOLERANCE_MODEL_DENSE


def test_constants_match_the_recorded_evidence_and_product_voice():
    """Os números do código vêm da evidência gravada, não de um valor mágico."""
    corpus = _load_corpus()
    assert corpus["voice"] == MEASURED_VOICE
    assert corpus["piper_version"] == MEASURED_PIPER_VERSION
    for path in EVIDENCE_RUNS:
        evidence = json.loads(path.read_text(encoding="utf-8"))
        assert evidence["voice"] == MEASURED_VOICE
        assert evidence["piper_version"] == MEASURED_PIPER_VERSION
        assert evidence["model_sha256"] == corpus["model_sha256"]

        pooled = evidence["pooled"]["effective_words_per_minute"]
        assert MEASURED_EFFECTIVE_WORDS_PER_MINUTE == pytest.approx(pooled, rel=TOLERANCE_EVIDENCE)
        regression = evidence["regression"]
        assert MEASURED_SPEECH_WORDS_PER_MINUTE == pytest.approx(
            regression["words_per_minute"], rel=TOLERANCE_EVIDENCE)
        # Pausa e overhead variam mais entre execuções: a constante é a média.
        assert MEASURED_PAUSE_SECONDS == pytest.approx(regression["seconds_per_pause"], abs=0.05)
        assert MEASURED_UTTERANCE_OVERHEAD_SECONDS == pytest.approx(
            regression["intercept_seconds"], abs=0.10)

    # O roteiro longo do corpus respeita o limite real de Scene.narration (400).
    assert len(_sample(corpus, "longo_480s")["texts"]) == 20
    assert all(len(text) <= 400 for text in _sample(corpus, "longo_480s")["texts"])


def test_runs_agree_on_the_synthesized_duration():
    """Execuções independentes do mesmo corpus: a duração do Piper é estável na tolerância."""
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in EVIDENCE_RUNS]
    by_run = [{s["id"]: s["measured_seconds"] for s in run["samples"]} for run in runs]
    assert all(set(ids) == set(by_run[0]) for ids in by_run)
    for sample_id in by_run[0]:
        seconds = [run[sample_id] for run in by_run]
        assert (max(seconds) - min(seconds)) / min(seconds) <= TOLERANCE_RUN_TO_RUN, sample_id