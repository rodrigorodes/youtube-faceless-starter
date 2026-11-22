"""QA determinístico do render a partir do plano + evidências (RP-030) — domínio puro.

A porta ``QualityEvaluator`` (``application/ports.py``) recebe o ``RenderPlan`` e a
**evidência** já medida — as métricas de mídia do ``FfmpegQa`` (ffprobe/ebur128/
silencedetect/blackdetect) e os ``AssetDescriptor`` resolvidos — e devolve o
``QualityReport`` versionado da F6 (``domain.qa_report.QaReport``): achados com
severidade ``blocking``/``warning``/``info`` e cobertura ``verified``/``not_verified``.
O adaptador (``adapters/quality_ffmpeg.py``) é quem toca a mídia; aqui a decisão é pura.

**O que este avaliador avalia de fato** (determinístico, sem provedor):

- **Técnica de mídia** — duração contra o plano e o formato, resolução, presença de
  áudio, loudness integrado (mistura e narração isolada), razão de silêncio e de preto.
  A régua é o ``domain.render.evaluate_qa`` existente (**não** duplicado): cada falha
  dele é traduzida num ``QaFinding`` com um ``check_id`` próprio.
- **Assets** — disponibilidade, licença e identidade conferidas contra o manifesto, com
  o ``domain.asset_resolver.verify_descriptor`` existente (reuso, não redigitação).
- **Plano (advisório)** — duração perto do limite do formato (``warning``), asset do
  manifesto sem uso (``warning``) e trilha de música silenciosa declarada (``info``).
- **Overlay (VE-05, técnico)** — quando o plano declara camadas, o QA confere o que é
  verificável sem IA: presença na janela, janela dentro do render/segmento base e
  tamanho/fit do asset. A medição vem do adaptador (ffprobe/ffmpeg) em
  ``OverlayEvidence``; sem medição a cobertura é ``not_verified``, nunca "sem overlay".

**O que este avaliador NÃO avalia** (declarado, nunca um score inventado):

- **Avaliação semântica multimodal** — "a imagem corresponde à narração?", "o
  enquadramento é agradável?", "a legenda está bem posicionada?". Isso exige um
  provedor/LLM de visão. A porta ``SemanticChecker`` (``application/ports.py``) recebe
  o resultado tipado (``SemanticResult``); sem provedor real o adaptador devolve
  ``not_verified`` e o achado é ``info``/``editorial``. O avaliador determinístico
  **não** devolve score visual e não finge cobertura: a ausência do provedor continua
  declarada em ``MULTIMODAL_EVALUATION`` e a falta de evidência vira cobertura
  ``not_verified``, nunca aprovação por omissão.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, get_args

from .asset_resolver import AssetDescriptor, AssetManifest, AssetResolutionError, check_fit, verify_descriptor
from .qa_report import QaCoverage, QaFinding, QaReport
from .render import _REQUIRED, MAX_SECONDS, evaluate_qa
from .render_plan import RenderPlan

# Estado da avaliação semântica multimodal. Não existe provedor de visão nesta fatia:
# declarar isto explicitamente é o oposto de inventar um score visual.
MULTIMODAL_EVALUATION = "out_of_scope_without_provider"

# Fração do limite de duração acima da qual o plano é sinalizado como perto da borda.
DURATION_MARGIN = 0.95

# Identificadores dos checks executados (um achado precisa referenciar um check em
# `checks_run` — exigência do contrato F6).
CHECK_MEDIA = "render.media_metrics"
CHECK_DURATION = "render.duration"
CHECK_RESOLUTION = "render.resolution"
CHECK_AUDIO = "render.audio_stream"
CHECK_LOUDNESS = "render.loudness"
CHECK_NARRATION = "render.narration"
CHECK_SILENCE = "render.silence"
CHECK_BLACK = "render.black_frames"
CHECK_ASSET = "render.asset_resolution"
CHECK_MANIFEST = "render.manifest"
CHECK_TIMELINE = "render.timeline"
CHECK_MUSIC = "render.music"
# VE-05: verificação técnica do overlay (presença/janela/tamanho) e a declaração
# explícita de que a avaliação semântica não foi verificada (sem provedor).
CHECK_OVERLAY = "render.overlay"
CHECK_SEMANTIC = "render.semantic"

# Fração mínima do quadro que a presença do overlay precisa alterar para não virar
# aviso. VE-01 desenha o overlay em tela cheia; abaixo disto ele é imperceptível.
MIN_OVERLAY_COVERAGE = 0.01

BLOCKING, WARNING, INFO = "blocking", "warning", "info"

# Resultado tipado da porta ``SemanticChecker`` (VE-05). "failed" é conteúdo que a
# verificação semântica **reprovou** (bloqueante); "not_verified" é ausência de
# verificação (sem provedor), nunca sinônimo de "passou".
SemanticVerdict = Literal["verified", "not_verified", "failed"]

# Prefixo da mensagem de `evaluate_qa` -> (check_id, severidade). Todo defeito de mídia
# medido é **bloqueante**: um vídeo mudo, curto, preto ou com resolução errada não
# publica. `test_quality.py` prova que nenhuma mensagem do `evaluate_qa` cai fora da
# tabela (senão a falha fechada a trata como bloqueante mesmo assim).
_FAILURE_RULES: tuple[tuple[str, str, str], ...] = (
    ("missing metric", CHECK_MEDIA, BLOCKING),
    ("no audio stream", CHECK_AUDIO, BLOCKING),
    ("audio is silent", CHECK_LOUDNESS, BLOCKING),
    ("audio too loud", CHECK_LOUDNESS, BLOCKING),
    ("narration is silent", CHECK_NARRATION, BLOCKING),
    ("narration has too much silence", CHECK_NARRATION, BLOCKING),
    ("too much silence", CHECK_SILENCE, BLOCKING),
    ("too much black", CHECK_BLACK, BLOCKING),
    ("duration", CHECK_DURATION, BLOCKING),
    ("resolution", CHECK_RESOLUTION, BLOCKING),
)

_ACTIONS = {
    CHECK_MEDIA: "Repetir a medição de QA do render.",
    CHECK_DURATION: "Revisar a duração da cena ou regenerar o render.",
    CHECK_RESOLUTION: "Renderizar na resolução do formato de saída.",
    CHECK_AUDIO: "Garantir que o render tenha faixa de áudio.",
    CHECK_LOUDNESS: "Corrigir a mixagem (silêncio ou estouro) antes de publicar.",
    CHECK_NARRATION: "Regenerar a narração: a voz isolada está muda ou com silêncio demais.",
    CHECK_SILENCE: "Revisar trechos silenciosos não intencionais na timeline.",
    CHECK_BLACK: "Revisar frames pretos não intencionais no vídeo.",
    CHECK_ASSET: "Resolver o asset no manifesto com licença e arquivo disponíveis.",
    CHECK_MANIFEST: "Remover do manifesto ou vincular a um shot.",
    CHECK_TIMELINE: "Revisar a duração do plano antes de publicar.",
    CHECK_MUSIC: "Nenhuma ação: trilha silenciosa declarada no plano.",
    CHECK_OVERLAY: "Revisar a camada de overlay: janela, presença e tamanho no vídeo renderizado.",
    CHECK_SEMANTIC: "Configurar um provedor de verificação semântica ou revisar o conteúdo manualmente.",
}

# `expected_s` não vem do analisador: o avaliador o deriva do próprio plano.
_MEASURED_KEYS = tuple(key for key in _REQUIRED if key != "expected_s")


@dataclass(frozen=True)
class SemanticResult:
    """Resultado tipado da verificação semântica (VE-05).

    ``verified`` é conteúdo conferido por um provedor real; ``not_verified`` é a
    ausência honesta de verificação (sem provedor); ``failed`` é reprovação semântica.
    ``not_verified`` e ``failed`` exigem motivo: um resultado sem motivo não é
    verificável e falha fechado na construção.
    """

    verdict: SemanticVerdict
    reason: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in get_args(SemanticVerdict):
            raise ValueError(f"unknown semantic verdict {self.verdict!r}")
        if self.verdict != "verified" and not (self.reason or "").strip():
            raise ValueError(f"a {self.verdict} semantic verdict requires a reason")


@dataclass(frozen=True)
class OverlayEvidence:
    """Medição técnica de uma camada de overlay no vídeo renderizado (VE-05).

    ``present`` é a presença medida na janela planejada; ``window_ok`` diz se a janela
    planejada é coerente com o render e o segmento base; ``coverage_ratio`` é a fração
    do quadro alterada pela camada (tamanho efetivo). ``measured=False`` representa uma
    medição que **não aconteceu** (falha do ffprobe/ffmpeg): o domínio a trata como
    ``not_verified``, nunca como "sem overlay" nem como aprovação por omissão.
    """

    shot_id: str
    scene_id: str
    start_s: float
    end_s: float
    present: bool = False
    window_ok: bool = True
    measured: bool = True
    coverage_ratio: float | None = None
    width: int | None = None
    height: int | None = None
    frame_width: int | None = None
    frame_height: int | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        for name in ("shot_id", "scene_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if not (isinstance(self.start_s, (int, float)) and not isinstance(self.start_s, bool)):
            raise ValueError("start_s must be a finite number")
        if not (isinstance(self.end_s, (int, float)) and not isinstance(self.end_s, bool)):
            raise ValueError("end_s must be a finite number")
        if not (math.isfinite(self.start_s) and math.isfinite(self.end_s)):
            raise ValueError("overlay evidence window must be finite")
        if self.start_s < 0 or self.end_s <= self.start_s:
            raise ValueError("overlay evidence window must be a positive interval")
        if self.coverage_ratio is not None:
            if not (isinstance(self.coverage_ratio, (int, float)) and not isinstance(self.coverage_ratio, bool)):
                raise ValueError("coverage_ratio must be a finite number")
            if not math.isfinite(self.coverage_ratio) or not (0.0 <= self.coverage_ratio <= 1.0):
                raise ValueError("coverage_ratio must be within [0, 1]")
        for name in ("width", "height", "frame_width", "frame_height"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value <= 0):
                raise ValueError(f"{name} must be a positive integer when provided")
        if not self.measured and not (self.reason or "").strip():
            raise ValueError("an unmeasured overlay requires a reason")


@dataclass(frozen=True)
class QualityEvidence:
    """Evidência medida fora do domínio: identidade do render + métricas + assets.

    ``render_id``/``checksum`` são a identidade **declarada** que a F6 amarra à
    aprovação (o checksum é o do conteúdo do mp4). ``media`` é o dicionário do
    ``QaAnalyzer`` — sem ``expected_s``, que o avaliador deriva do plano. ``assets`` são
    os descriptors resolvidos, conferidos contra o manifesto do plano. ``generated_at``
    é o instante do relatório (default: agora, com fuso).

    ``overlays`` e ``semantic`` são aditivos (VE-05): vazios/``None`` significam "não
    medido", exatamente o comportamento anterior — plano sem overlay e sem verificador
    semântico produz o mesmo relatório de sempre.
    """

    render_id: str
    checksum: str
    media: Mapping[str, object] | None = None
    assets: tuple[AssetDescriptor, ...] = ()
    generated_at: datetime | None = None
    overlays: tuple[OverlayEvidence, ...] = ()
    semantic: SemanticResult | None = None


def evaluate_quality(plan: RenderPlan, evidence: QualityEvidence) -> QaReport:
    """Avalia o render do ``plan`` a partir da ``evidence`` e devolve o QualityReport.

    Fail-closed: sem métricas completas ou sem os descriptors dos assets referenciados a
    cobertura fica ``not_verified`` (nada executado não é evidência de qualidade). Com a
    evidência completa a cobertura fica ``verified`` e só achados ``blocking`` impedem a
    aprovação.
    """
    if not isinstance(plan, RenderPlan):
        raise TypeError("plan must be a RenderPlan")
    if not isinstance(evidence, QualityEvidence):
        raise TypeError("evidence must be a QualityEvidence")

    checks: list[str] = []
    findings: list[QaFinding] = []
    gaps: list[str] = []

    _collect_media_checks(plan, evidence, checks, findings, gaps)
    _collect_asset_checks(plan, evidence, checks, findings, gaps)
    _collect_overlay_checks(plan, evidence, checks, findings, gaps)
    _collect_semantic_checks(evidence, checks, findings)
    _collect_plan_advisories(plan, checks, findings)

    coverage = (
        QaCoverage(status="not_verified", reason=_join_gaps(gaps))
        if gaps
        else QaCoverage(status="verified")
    )
    return QaReport(
        render_id=evidence.render_id,
        checksum=evidence.checksum,
        generated_at=evidence.generated_at or datetime.now(timezone.utc),
        coverage=coverage,
        checks_run=tuple(dict.fromkeys(checks)),
        findings=tuple(findings),
    )


def _collect_media_checks(plan, evidence, checks, findings, gaps) -> None:
    media = evidence.media
    if media is None:
        gaps.append("no media metrics were measured for the render")
        return
    missing = [key for key in _MEASURED_KEYS if key not in media]
    if missing:
        gaps.append("incomplete media metrics: " + ", ".join(missing))
        return
    metrics = {key: media[key] for key in _MEASURED_KEYS}
    expected = plan.timeline.duration_ticks / plan.timeline.ticks_per_second
    report = evaluate_qa({**metrics, "expected_s": round(expected, 3)}, plan.output.format)
    checks.append(CHECK_MEDIA)
    for index, failure in enumerate(report.failures):
        check_id, severity = _classify(failure)
        checks.append(check_id)
        findings.append(_finding(f"media-{index}", check_id, severity, failure))


def _collect_asset_checks(plan, evidence, checks, findings, gaps) -> None:
    referenced = {shot.asset_ref for scene in plan.timeline.scenes for shot in scene.shots}
    descriptors = tuple(evidence.assets)
    if not descriptors:
        gaps.append("no resolved asset descriptors were provided")
        return
    resolved = {descriptor.asset_id for descriptor in descriptors}
    unresolved = sorted(referenced - resolved)
    if unresolved:
        gaps.append("assets not resolved: " + ", ".join(unresolved))
    manifest = AssetManifest.of(plan)
    for index, descriptor in enumerate(descriptors):
        try:
            verify_descriptor(manifest, descriptor)
        except AssetResolutionError as exc:
            checks.append(CHECK_ASSET)
            findings.append(_finding(f"asset-{index}", CHECK_ASSET, BLOCKING, str(exc)))
        else:
            checks.append(CHECK_ASSET)


def _collect_overlay_checks(plan, evidence, checks, findings, gaps) -> None:
    """Verificação técnica das camadas de overlay (VE-05), por cima do QA de hoje.

    Plano sem overlay não acrescenta check, achado nem lacuna: o relatório é idêntico
    ao de hoje. Com overlay, a ausência de medição é ``not_verified`` (não há evidência
    de que a camada apareceu) e os defeitos medidos — janela fora do render/base,
    camada ausente, tamanho incompatível — são ``blocking``.
    """
    planned = [(scene, shot) for scene in plan.timeline.scenes for shot in scene.overlay_shots]
    if not planned:
        return
    if not evidence.overlays:
        gaps.append("no overlay evidence was measured for the render")
        return
    measured = {item.shot_id: item for item in evidence.overlays}
    descriptors = {descriptor.asset_id: descriptor for descriptor in evidence.assets}
    tps = plan.timeline.ticks_per_second
    for scene, shot in planned:
        checks.append(CHECK_OVERLAY)
        item = measured.get(shot.shot_id)
        expected_start = shot.start_tick / tps
        expected_end = (shot.start_tick + shot.duration_ticks) / tps
        if item is None:
            gaps.append(f"overlay {shot.shot_id} was not measured")
            continue
        if abs(item.start_s - expected_start) > 0.001 or abs(item.end_s - expected_end) > 0.001:
            findings.append(_finding(
                f"overlay-window-evidence-{scene.scene_id}-{shot.shot_id}", CHECK_OVERLAY, BLOCKING,
                f"overlay {shot.shot_id} was measured at {item.start_s:.3f}-{item.end_s:.3f}s, "
                f"but the plan puts it at {expected_start:.3f}-{expected_end:.3f}s",
            ))
        if not item.measured:
            gaps.append(item.reason or f"overlay {shot.shot_id} could not be measured")
            continue
        if scene.host_base_for(shot) is None:
            findings.append(_finding(
                f"overlay-host-{scene.scene_id}-{shot.shot_id}", CHECK_OVERLAY, BLOCKING,
                f"overlay {shot.shot_id} crosses a base segment boundary",
            ))
        if not item.window_ok:
            findings.append(_finding(
                f"overlay-window-{scene.scene_id}-{shot.shot_id}", CHECK_OVERLAY, BLOCKING,
                item.reason or f"overlay {shot.shot_id} is outside its render/base window",
            ))
        if not item.present:
            findings.append(_finding(
                f"overlay-presence-{scene.scene_id}-{shot.shot_id}", CHECK_OVERLAY, BLOCKING,
                item.reason or f"overlay {shot.shot_id} is not visible in its window",
            ))
        descriptor = descriptors.get(shot.asset_ref)
        if descriptor is not None:
            fit = shot.composition.fit if shot.composition is not None else "cover"
            try:
                check_fit(descriptor, plan.output, fit=fit, shot_duration_ticks=shot.duration_ticks)
            except AssetResolutionError as exc:
                findings.append(_finding(
                    f"overlay-size-{scene.scene_id}-{shot.shot_id}", CHECK_OVERLAY, BLOCKING, str(exc),
                ))
        if item.coverage_ratio is not None and item.coverage_ratio < MIN_OVERLAY_COVERAGE:
            findings.append(_finding(
                f"overlay-coverage-{scene.scene_id}-{shot.shot_id}", CHECK_OVERLAY, WARNING,
                f"overlay {shot.shot_id} changes only {item.coverage_ratio:.1%} of the frame",
            ))


def _collect_semantic_checks(evidence, checks, findings) -> None:
    """Declara a cobertura semântica (VE-05) sem inventar aprovação.

    Sem resultado semântico não há check nem achado: o comportamento de hoje fica
    intacto. Com resultado, ``not_verified`` vira ``info`` (a semântica não foi
    verificada), ``failed`` vira ``blocking`` (a semântica reprovou) e ``verified`` não
    produz achado — em nenhum caso o relatório afirma qualidade visual que não mediu.
    """
    result = evidence.semantic
    if result is None:
        return
    checks.append(CHECK_SEMANTIC)
    if result.verdict == "failed":
        findings.append(_finding("semantic-failed", CHECK_SEMANTIC, BLOCKING, result.reason, category="editorial"))
    elif result.verdict == "not_verified":
        findings.append(_finding("semantic-not-verified", CHECK_SEMANTIC, INFO, result.reason, category="editorial"))


def _collect_plan_advisories(plan, checks, findings) -> None:
    checks.append(CHECK_TIMELINE)
    fmt = plan.output.format
    seconds = plan.timeline.duration_ticks / plan.timeline.ticks_per_second
    limit = MAX_SECONDS[fmt]
    if seconds > DURATION_MARGIN * limit:
        findings.append(_finding(
            "plan-duration-margin", CHECK_TIMELINE, WARNING,
            f"plan lasts {seconds:.1f}s, within 5% of the {limit}s limit for {fmt.value}",
        ))
    referenced = {shot.asset_ref for scene in plan.timeline.scenes for shot in scene.shots}
    unused = sorted({asset.asset_id for asset in plan.asset_manifest} - referenced)
    if unused:
        checks.append(CHECK_MANIFEST)
        findings.append(_finding(
            "plan-orphan-assets", CHECK_MANIFEST, WARNING,
            "manifest assets used by no shot: " + ", ".join(unused),
        ))
    if any(source.kind == "music" and source.silent for source in plan.generated_audio):
        checks.append(CHECK_MUSIC)
        findings.append(_finding(
            "plan-silent-music", CHECK_MUSIC, INFO,
            "the music track is silent by plan (music=False)",
        ))


def _classify(failure: str) -> tuple[str, str]:
    for prefix, check_id, severity in _FAILURE_RULES:
        if failure.startswith(prefix):
            return check_id, severity
    return CHECK_MEDIA, BLOCKING  # desconhecido: falha fechada, nunca aprova por omissão


def _finding(finding_id: str, check_id: str, severity: str, evidence: str,
             category: str = "technical") -> QaFinding:
    return QaFinding(
        finding_id=finding_id,
        check_id=check_id,
        category=category,
        severity=severity,
        evidence=evidence,
        suggested_action=_ACTIONS.get(check_id, "Revisar o render antes de publicar."),
    )


def _join_gaps(gaps: list[str]) -> str:
    return "; ".join(gaps)[:500]
