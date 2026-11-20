"""Contrato puro do relatório de QA e do gate de aprovação por versão (F6-06/F6-07).

Este módulo representa, de forma versionada e imutável, os achados de QA de um
render e a decisão de aprovação. Ele não executa checks de mídia, não lê nem
grava nada, não chama ffmpeg e não publica. A regra que ele garante é a do
critério de aceite da F6: **a versão aprovada é exatamente a versão passível de
publicação**.

Fronteiras deliberadas:

- **Check executado x achado.** ``QaReport.checks_run`` declara quais checks
  foram executados; ``QaFinding`` descreve um problema encontrado por um desses
  checks. Todo achado precisa referenciar um ``check_id`` presente em
  ``checks_run``: o contrato não aceita achado de origem desconhecida. Nada aqui
  executa o check nem confirma que ele de fato rodou — o chamador declara a
  cobertura (ver "Limites" abaixo).
- **Cobertura não verificada x verificada sem problemas.** ``coverage`` tem
  estado explícito (``verified``/``not_verified``) e motivo obrigatório quando
  não verificado. Relatório sem nenhum check executado não pode se declarar
  ``verified``; relatório ``not_verified`` é representável mas **não aprovável**.
  Ausência de achados não é evidência de qualidade — a mesma lição de custo
  desconhecido x custo zero e de dado medido x dado indisponível.
- **Severidade fechada.** ``severity`` é exatamente ``blocking``, ``warning`` ou
  ``info``. Não há severidade livre em texto, nem escalas numéricas. Só
  ``blocking`` impede a publicação; ``warning`` e ``info`` aparecem contabilizados
  em ``severity_counts`` (zero explícito, não chave ausente).
- **Aprovação vinculada à versão.** ``approve``/``assert_publishable`` recebem a
  identidade do render mais recente (``latest``), a identidade que se pretende
  aprovar (``requested``) e o relatório QA. A aprovação só passa se as três
  identidades coincidirem, a cobertura estiver verificada e não houver
  ``blocking``. Aprovar um render superado é recusado mesmo com relatório limpo.
  Cada motivo de recusa tem erro próprio (todos subclasse de ``QaGateError``).
- **Identidade é declarada, não recalculada.** O contrato não recalcula o
  checksum do artefato nem confere o algoritmo do digest: só exige identidade
  não vazia e consistente. Quem calcula o checksum é o renderer.

Limites explícitos: este contrato **não verifica se os checks foram realmente
executados**, não valida o conteúdo de mídia (codec, frame preto, loudness etc.)
e não substitui F6-04/F6-05. Ele só representa os identificadores dos checks, a
severidade, a evidência e a ação sugerida, e recusa estados incoerentes.

Nota de integração: já existe um ``QaReport`` legado em ``domain/contracts.py``
(``passed``/``failures``/``metrics``) usado pelo render atual. Este módulo é o
contrato novo e vinculado à versão da F6 e **não** substitui nem altera aquele;
a adoção pelo runtime é trabalho de outra fatia.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_validator,
    model_validator,
)

from .contracts import _Model

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Severity = Literal["blocking", "warning", "info"]
FindingCategory = Literal["technical", "editorial"]
CoverageStatus = Literal["verified", "not_verified"]

# Severidades na ordem canônica; toda contagem sai com as três chaves, mesmo
# zeradas (zero medido é diferente de chave ausente).
SEVERITIES: tuple[Severity, ...] = ("blocking", "warning", "info")


def _finite_aware_instant(value: object, name: str) -> datetime:
    """Exige ``datetime`` com fuso e timestamp representável/finito."""
    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    try:
        timestamp = value.timestamp()
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"{name} must be a representable finite instant") from exc
    if not math.isfinite(timestamp):
        raise ValueError(f"{name} must be a representable finite instant")
    return value


class QaFinding(BaseModel):
    """Achado de um check: categoria, severidade, evidência e ação sugerida (F6-06).

    Evidência é obrigatória e não vazia: achado sem evidência não é verificável.
    ``suggested_action`` é a correção sugerida ao operador; é sempre uma sugestão,
    nunca aplicada por este contrato.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: NonBlank
    category: FindingCategory
    severity: Severity
    evidence: NonBlank
    suggested_action: NonBlank


class QaCoverage(BaseModel):
    """Cobertura declarada do QA: distingue "não verificado" de "verificado sem problemas"."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: CoverageStatus
    reason: NonBlank | None = None

    @model_validator(mode="after")
    def _reason_matches_status(self):
        if self.status == "not_verified":
            if self.reason is None:
                raise ValueError("not_verified coverage requires a reason")
        elif self.reason is not None:
            raise ValueError("verified coverage must not declare a gap reason")
        return self


class QaReport(_Model):
    """Relatório de QA vinculado a um render por ``render_id`` + ``checksum``.

    Valida apenas a coerência interna: identidade não vazia, cobertura declarada,
    achados únicos e rastreáveis a um check executado. Não executa nem confirma
    nenhum check.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    render_id: NonBlank
    checksum: NonBlank
    generated_at: datetime
    coverage: QaCoverage
    checks_run: tuple[NonBlank, ...] = ()
    findings: tuple[QaFinding, ...] = ()

    @field_validator("generated_at")
    @classmethod
    def _aware_and_finite(cls, value: datetime) -> datetime:
        return _finite_aware_instant(value, "generated_at")

    @model_validator(mode="after")
    def _coherent(self):
        if len(set(self.checks_run)) != len(self.checks_run):
            raise ValueError("checks_run must not repeat a check_id")
        seen: set[str] = set()
        for item in self.findings:
            if item.check_id in seen:
                raise ValueError(f"duplicate check_id {item.check_id!r}")
            seen.add(item.check_id)
        if self.coverage.status == "verified" and not self.checks_run:
            raise ValueError(
                "a verified report requires at least one executed check; "
                "no executed check is not evidence of quality"
            )
        unknown = seen - set(self.checks_run)
        if unknown:
            raise ValueError(
                f"findings must reference executed checks; not executed: {sorted(unknown)!r}"
            )
        return self

    @property
    def severity_counts(self) -> dict[Severity, int]:
        """Contagem por severidade com as três chaves sempre presentes (zero explícito)."""
        counts: dict[Severity, int] = {severity: 0 for severity in SEVERITIES}
        for item in self.findings:
            counts[item.severity] += 1
        return counts

    @property
    def blocking_findings(self) -> tuple[QaFinding, ...]:
        return tuple(item for item in self.findings if item.severity == "blocking")

    @property
    def is_publishable(self) -> bool:
        """Verdadeiro somente sem achados ``blocking``.

        ``warning`` e ``info`` não bloqueiam, mas continuam contabilizados em
        ``severity_counts``. Cobertura e vínculo de versão são regras do gate
        (``assert_publishable``), não desta propriedade do relatório.
        """
        return not self.blocking_findings


class QaGateError(ValueError):
    """Erro base do gate de aprovação por versão."""


class InvalidRenderId(QaGateError):
    """``render_id`` vazio ou de tipo inválido."""


class InvalidChecksum(QaGateError):
    """``checksum`` vazio ou de tipo inválido."""


class InvalidGeneratedAt(QaGateError):
    """Instante de geração do relatório inválido (ingênuo, não finito ou de outro tipo)."""


class RenderSuperseded(QaGateError):
    """O render pretendido não é o mais recente: já existe nova versão."""


class ReportForOtherRender(QaGateError):
    """O relatório QA não corresponde ao render que se pretende aprovar."""


class CoverageNotVerified(QaGateError):
    """Relatório sem cobertura verificada: nada executado não é aprovável."""


class BlockingFindings(QaGateError):
    """Há achados ``blocking``: o render não é publicável."""


@dataclass(frozen=True)
class RenderVersion:
    """Identidade declarada de um render.

    Transporta ``render_id`` e ``checksum`` sem validar: quem valida é o gate
    (``approve``/``assert_publishable``), que levanta ``InvalidRenderId`` ou
    ``InvalidChecksum`` com motivo próprio.
    """

    render_id: str
    checksum: str


def _require_identity(render_id: object, checksum: object, what: str) -> None:
    if not isinstance(render_id, str) or not render_id.strip():
        raise InvalidRenderId(f"{what} render_id must not be blank")
    if not isinstance(checksum, str) or not checksum.strip():
        raise InvalidChecksum(f"{what} checksum must not be blank")


def _effective(report: QaReport) -> tuple[str, str]:
    """Identidade do relatório, tolerando modelo contornado (``model_construct``)."""
    render_id = getattr(report, "render_id", None)
    checksum = getattr(report, "checksum", None)
    _require_identity(render_id, checksum, "report")
    return render_id.strip(), checksum.strip()


def _require_verified_coverage(report: QaReport) -> None:
    coverage = getattr(report, "coverage", None)
    if coverage is None or getattr(coverage, "status", None) != "verified":
        raise CoverageNotVerified(
            "the QA report does not declare a verified coverage; "
            "no executed check is not evidence of quality"
        )
    if not getattr(report, "checks_run", ()):
        raise CoverageNotVerified(
            "a verified report requires at least one executed check; "
            "no executed check is not evidence of quality"
        )


def _require_valid_instant(report: QaReport) -> None:
    try:
        _finite_aware_instant(getattr(report, "generated_at", None), "generated_at")
    except ValueError as exc:
        raise InvalidGeneratedAt(str(exc)) from exc


def approve(
    *,
    report: QaReport,
    latest: RenderVersion,
    requested: RenderVersion,
) -> RenderVersion:
    """Aprova ``requested`` e devolve a identidade exata que a publicação deve usar.

    Recusa, nesta ordem, cada motivo com um erro próprio:

    1. identidade de render/checksum vazia (``InvalidRenderId``/``InvalidChecksum``);
    2. instante de geração inválido (``InvalidGeneratedAt``);
    3. cobertura não verificada (``CoverageNotVerified``);
    4. ``requested`` diferente do mais recente (``RenderSuperseded``);
    5. relatório de outro render (``ReportForOtherRender``);
    6. achados ``blocking`` (``BlockingFindings``).

    O retorno é a identidade que o ato de publicar deve reutilizar, sem
    reconsultar "o mais recente" depois — evita aprovar uma versão e publicar
    outra que surgiu no meio do caminho.
    """
    _require_identity(latest.render_id, latest.checksum, "latest")
    _require_identity(requested.render_id, requested.checksum, "requested")
    report_render_id, report_checksum = _effective(report)
    _require_valid_instant(report)
    _require_verified_coverage(report)

    if (
        requested.render_id.strip() != latest.render_id.strip()
        or requested.checksum.strip() != latest.checksum.strip()
    ):
        raise RenderSuperseded(
            f"render {requested.render_id!r}/{requested.checksum!r} is not the latest "
            f"{latest.render_id!r}/{latest.checksum!r}; re-run QA on the latest render"
        )
    if report_render_id != requested.render_id.strip() or report_checksum != requested.checksum.strip():
        raise ReportForOtherRender(
            f"QA report covers {report_render_id!r}/{report_checksum!r}, "
            f"not the approved render {requested.render_id!r}/{requested.checksum!r}"
        )
    if not report.is_publishable:
        blockers = ", ".join(sorted(item.check_id for item in report.blocking_findings))
        raise BlockingFindings(f"blocking QA findings prevent approval: {blockers}")

    return RenderVersion(render_id=requested.render_id.strip(), checksum=requested.checksum.strip())


def assert_publishable(
    *,
    report: QaReport,
    latest: RenderVersion,
    requested: RenderVersion,
) -> None:
    """Igual a ``approve``, mas apenas valida: levanta o erro do motivo, sem retorno."""
    approve(report=report, latest=latest, requested=requested)
