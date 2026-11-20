"""Contrato puro do relatório de QA e do gate de aprovação por versão (F6-06/F6-07).

Este módulo representa, de forma versionada e imutável, os achados de QA de um
render e a decisão de aprovação. Ele não executa checks de mídia, não lê nem
grava nada, não chama ffmpeg e não publica. A regra do critério de aceite da F6
— **a versão aprovada é exatamente a versão passível de publicação** — é
garantida **no caminho do contrato**, dado que ``latest`` seja verdadeiro e que
a publicação use o valor retornado por ``approve``.

Fronteiras deliberadas:

- **Check executado x achado.** ``QaReport.checks_run`` declara quais checks
  foram executados; ``QaFinding`` descreve um problema encontrado por um desses
  checks. ``finding_id`` identifica o achado e ``check_id`` identifica o check:
  um mesmo check pode legitimamente produzir vários achados com evidências e
  ações distintas, mas ``finding_id`` é único. Todo achado precisa referenciar
  um ``check_id`` presente em ``checks_run``: o contrato não aceita achado de
  origem desconhecida. Nada aqui executa o check nem confirma que ele rodou — o
  chamador declara a cobertura (ver "Limites" abaixo).
- **Cobertura não verificada x verificada sem problemas.** ``coverage`` tem
  estado explícito (``verified``/``not_verified``) e motivo obrigatório quando
  não verificado. Relatório sem nenhum check executado não pode se declarar
  ``verified``; relatório ``not_verified`` é representável mas **não aprovável**
  nem publicável. Ausência de achados não é evidência de qualidade — a mesma
  lição de custo desconhecido x custo zero e de dado medido x dado indisponível.
- **Severidade fechada e falha fechada.** ``severity`` é exatamente ``blocking``,
  ``warning`` ou ``info``. Não há severidade livre em texto, nem escalas
  numéricas. Só ``blocking`` impede a publicação; ``warning`` e ``info``
  aparecem contabilizados em ``severity_counts`` (zero explícito, não chave
  ausente). Como ``model_copy``/``model_construct`` contornam a validação,
  qualquer severidade fora de ``warning``/``info`` é tratada como bloqueante por
  ``is_publishable`` e contabilizada em ``blocking`` — a propriedade nunca falha
  aberta.
- **Aprovação vinculada à versão.** ``approve``/``assert_publishable`` recebem a
  identidade do render mais recente (``latest``), a identidade que se pretende
  aprovar (``requested``) e o relatório QA. A aprovação só passa se as três
  identidades coincidirem, a cobertura estiver verificada, o estado do relatório
  revalidar e não houver achados bloqueantes. Aprovar um render superado é
  recusado mesmo com relatório limpo. Cada motivo de recusa tem erro próprio
  (todos subclasse de ``QaGateError``).
- **Identidade é declarada, não recalculada nem normalizada.** ``render_id`` e
  ``checksum`` são identidades exatas: espaços nas bordas e caracteres
  invisíveis são recusados, nunca removidos silenciosamente. O retorno de
  ``approve`` é a identidade de ``requested`` como recebida. O contrato não
  recalcula o checksum do artefato nem confere o algoritmo do digest: qualquer
  string não vazia e visível passa. Quem calcula o checksum é o renderer.
- **Texto visível.** Identificadores, motivo de cobertura, ação sugerida e
  evidência recusam ``Cc``/``Cf``/``Cs`` (controle, formato — inclui ZWSP, ZWNJ,
  BOM e override bidi — e surrogates) e os separadores ``Zl``/``Zp``
  (U+2028/U+2029). Identidades também recusam qualquer espaço Unicode interior
  (espaço comum, NBSP U+00A0, U+3000). ``\\n`` é aceito somente em evidência.
- **Estado contornado é revalidado, não presumido.** ``model_copy`` e
  ``model_construct`` pulam a validação do modelo e ``frozen``. O gate não
  decide sobre o objeto vivo: exige que ``findings`` e ``checks_run`` sejam
  exatamente ``tuple`` (lista, conjunto, dict e iterador de uso único são
  recusados com ``InvalidReportState``), materializa uma única cópia canônica
  com ``model_dump``/``model_validate`` e decide sempre sobre ela. Se a
  revalidação produzir um relatório semanticamente equivalente, ele é usado; se
  não, é recusado. A garantia de imutabilidade e de tipos vale para o caminho
  ``model_validate``/``load_versioned``.

Limites explícitos: este contrato **não verifica se os checks foram realmente
executados**, não valida o conteúdo de mídia (codec, frame preto, loudness etc.)
e não substitui F6-04/F6-05. Ele só representa os identificadores dos checks, a
severidade, a evidência e a ação sugerida, e recusa estados incoerentes.

Limites do gate, para não superestimar a garantia:

- ``latest`` é declaração do chamador; o contrato não tem fonte de verdade sobre
  qual é o render mais recente. Se o chamador mentir, o gate não detecta.
- ``checksum`` é identidade declarada (qualquer string não vazia e visível
  passa), não digest recalculado.
- ``generated_at`` futuro é aceito e não é usado para frescor/idade do relatório.
- ``model_copy``/``model_construct`` contornam ``frozen`` e a validação do
  modelo: a garantia de imutabilidade/tipos vale para o caminho
  ``model_validate``/``load_versioned``. O gate revalida o relatório antes de
  decidir: estado contornado é **revalidado**; se a revalidação produzir um
  relatório semanticamente equivalente, ele é usado, e se não, é recusado
  (``InvalidReportState``). ``findings``/``checks_run`` que não sejam
  exatamente ``tuple`` são recusados antes de qualquer leitura.
- **Falsos positivos conscientes de ``Cc``/``Cf``/``Zl``/``Zp``.** A disciplina
  de texto recusa ``ZWNJ`` em texto legítimo como o persa ``میخواهم``, ``ZWJ``
  em emoji e ``RLM``, além de ``\\r\\n`` e tab em evidência. Isso é uma troca
  deliberada por previsibilidade: o produtor de QA redige a evidência, e
  ``ffprobe`` em Linux não emite CRLF. Uma fatia futura pode permitir ``\\r\\n``
  e tab **apenas** em evidência, com teste próprio, se o fluxo real exigir.

Nota de integração: já existe um ``QaReport`` legado em ``domain/contracts.py``
(``passed``/``failures``/``metrics``) usado pelo render atual. Este módulo é o
contrato novo e vinculado à versão da F6 e **não** substitui nem altera aquele;
a adoção pelo runtime é trabalho de outra fatia.
"""

import math
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from .contracts import _Model

Severity = Literal["blocking", "warning", "info"]
FindingCategory = Literal["technical", "editorial"]
CoverageStatus = Literal["verified", "not_verified"]

# Severidades na ordem canônica; toda contagem sai com as três chaves, mesmo
# zeradas (zero medido é diferente de chave ausente).
SEVERITIES: tuple[Severity, ...] = ("blocking", "warning", "info")
# Só estas duas deixam de bloquear. Qualquer outro valor — inclusive estado
# contornado por model_copy — é bloqueante (falha fechada).
NON_BLOCKING_SEVERITIES: tuple[str, ...] = ("warning", "info")
INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})
# Separadores de linha/parágrafo Unicode: quebra ambígua em log é vetor de
# confusão, então são recusados até em evidência (onde só "\n" é permitido).
AMBIGUOUS_LINE_BREAK_CATEGORIES = frozenset({"Zl", "Zp"})


def _reject_unsafe_characters(value: str, *, allow_newline: bool = False) -> str:
    """Recusa controle, formato e surrogate que quebram ou disfarçam texto.

    ``Cf`` inclui ZWSP (U+200B), ZWNJ (U+200C), BOM (U+FEFF) e override
    bidirecional; ``Cc`` cobre nulos e tabulações; ``Cs`` cobre surrogates
    isolados. Apenas ``\\n`` é permitido quando o chamador declara que faz
    sentido (evidência).
    """
    for character in value:
        if character == "\n" and allow_newline:
            continue
        if unicodedata.category(character) in INVISIBLE_CATEGORIES:
            raise ValueError("text must not contain control, format or surrogate characters")
    return value


def _reject_ambiguous_line_breaks(value: str) -> str:
    for character in value:
        if unicodedata.category(character) in AMBIGUOUS_LINE_BREAK_CATEGORIES:
            raise ValueError("text must not contain Unicode line or paragraph separators")
    return value


def _identity_text(value: str) -> str:
    """Identidade exata: um token sem espaços (nem invisíveis) em qualquer posição."""
    if value != value.strip():
        raise ValueError("identity must not have leading or trailing whitespace")
    if any(character.isspace() for character in value):
        raise ValueError("identity must not contain whitespace")
    _reject_unsafe_characters(value)
    return _reject_ambiguous_line_breaks(value)


def _single_line_text(value: str) -> str:
    _reject_unsafe_characters(value)
    return _reject_ambiguous_line_breaks(value)


def _multiline_text(value: str) -> str:
    _reject_unsafe_characters(value, allow_newline=True)
    return _reject_ambiguous_line_breaks(value)


Identity = Annotated[str, StringConstraints(min_length=1), AfterValidator(_identity_text)]
SingleLineText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1), AfterValidator(_single_line_text)
]
EvidenceText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1), AfterValidator(_multiline_text)
]


def _is_check_identifier(value: object) -> bool:
    """Mesma disciplina de ``Identity``, para tolerar estado contornado sem estourar."""
    try:
        if not isinstance(value, str) or not value:
            return False
        _identity_text(value)
    except (TypeError, ValueError):
        return False
    return True


def _has_executed_check(checks_run: object) -> bool:
    """Falha fechada: exige ``tuple`` exata com ao menos um check válido e visível."""
    if type(checks_run) is not tuple:
        return False
    return any(_is_check_identifier(item) for item in checks_run)


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

    ``finding_id`` identifica o achado; ``check_id`` identifica o check que o
    produziu. Dois achados do mesmo check são válidos desde que tenham
    ``finding_id`` distintos. Evidência é obrigatória e não vazia: achado sem
    evidência não é verificável. ``suggested_action`` é a correção sugerida ao
    operador; é sempre uma sugestão, nunca aplicada por este contrato.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: Identity
    check_id: Identity
    category: FindingCategory
    severity: Severity
    evidence: EvidenceText
    suggested_action: SingleLineText


class QaCoverage(BaseModel):
    """Cobertura declarada do QA: distingue "não verificado" de "verificado sem problemas"."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: CoverageStatus
    reason: SingleLineText | None = None

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

    Valida apenas a coerência interna: identidade exata e visível, cobertura
    declarada, ``finding_id``/``checks_run`` únicos e achados rastreáveis a um
    check executado. Não executa nem confirma nenhum check.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    render_id: Identity
    checksum: Identity
    generated_at: datetime
    coverage: QaCoverage
    checks_run: tuple[Identity, ...] = ()
    findings: tuple[QaFinding, ...] = ()

    @field_validator("generated_at")
    @classmethod
    def _aware_and_finite(cls, value: datetime) -> datetime:
        return _finite_aware_instant(value, "generated_at")

    @model_validator(mode="after")
    def _coherent(self):
        if len(set(self.checks_run)) != len(self.checks_run):
            raise ValueError("checks_run must not repeat a check_id")
        finding_ids: set[str] = set()
        referenced: set[str] = set()
        for item in self.findings:
            if item.finding_id in finding_ids:
                raise ValueError(f"duplicate finding_id {item.finding_id!r}")
            finding_ids.add(item.finding_id)
            referenced.add(item.check_id)
        if self.coverage.status == "verified" and not self.checks_run:
            raise ValueError(
                "a verified report requires at least one executed check; "
                "no executed check is not evidence of quality"
            )
        unknown = referenced - set(self.checks_run)
        if unknown:
            raise ValueError(
                f"findings must reference executed checks; not executed: {sorted(unknown)!r}"
            )
        return self

    @property
    def severity_counts(self) -> dict[Severity, int]:
        """Contagem por severidade com as três chaves sempre presentes (zero explícito).

        Severidade desconhecida (estado contornado) é contada como ``blocking``:
        a contagem falha fechada e nunca levanta ``KeyError``.
        """
        counts: dict[Severity, int] = {severity: 0 for severity in SEVERITIES}
        if type(getattr(self, "findings", None)) is not tuple:
            # Coleção contornada (lista, set, dict, iterador de uso único): não
            # dá para enumerar com segurança; conta um bloqueio não verificável.
            counts["blocking"] += 1
            return counts
        for item in self.findings:
            severity = getattr(item, "severity", None)
            key = severity if severity in SEVERITIES else "blocking"
            counts[key] += 1
        return counts

    @property
    def blocking_findings(self) -> tuple[QaFinding, ...]:
        """Achados que impedem a publicação — falha fechada para estado contornado."""
        if type(getattr(self, "findings", None)) is not tuple:
            # Iterador de uso único consumiria a decisão; trata como bloqueio.
            return (self.findings,)
        return tuple(
            item
            for item in self.findings
            if getattr(item, "severity", None) not in NON_BLOCKING_SEVERITIES
        )

    @property
    def is_publishable(self) -> bool:
        """Relatório publicável: cobertura verificada com check executado e sem ``blocking``.

        Cobre o que o relatório pode decidir sozinho. ``findings``/``checks_run``
        fora de ``tuple`` contam como bloqueio (falha fechada, sem consumir
        iterador): a propriedade nunca aprova estado contornado. O vínculo com a
        versão mais recente continua sendo regra exclusiva do gate
        (``approve``/``assert_publishable``), que também revalida o estado.
        """
        coverage = getattr(self, "coverage", None)
        if getattr(coverage, "status", None) != "verified":
            return False
        if not _has_executed_check(getattr(self, "checks_run", ())):
            return False
        return not self.blocking_findings


class QaGateError(ValueError):
    """Erro base do gate de aprovação por versão."""


class InvalidRenderId(QaGateError):
    """``render_id`` vazio, com espaço nas bordas ou com caractere invisível."""


class InvalidChecksum(QaGateError):
    """``checksum`` vazio, com espaço nas bordas ou com caractere invisível."""


class InvalidRenderVersion(QaGateError):
    """``latest`` ou ``requested`` não é um ``RenderVersion``."""


class InvalidGeneratedAt(QaGateError):
    """Instante de geração do relatório inválido (ingênuo, não finito ou de outro tipo)."""


class InvalidReportState(QaGateError):
    """Relatório com estado interno contornado (ex.: achado ou severidade inválidos)."""


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
    ``InvalidChecksum`` com motivo próprio. A identidade é usada como recebida,
    sem normalização.
    """

    render_id: str
    checksum: str


def _require_render_version(value: object, what: str) -> RenderVersion:
    if not isinstance(value, RenderVersion):
        raise InvalidRenderVersion(f"{what} must be a RenderVersion")
    return value


def _require_identity(render_id: object, checksum: object, what: str) -> None:
    if not isinstance(render_id, str) or not render_id:
        raise InvalidRenderId(f"{what} render_id must not be blank")
    try:
        _identity_text(render_id)
    except ValueError as exc:
        raise InvalidRenderId(f"{what} render_id is invalid: {exc}") from exc
    if not isinstance(checksum, str) or not checksum:
        raise InvalidChecksum(f"{what} checksum must not be blank")
    try:
        _identity_text(checksum)
    except ValueError as exc:
        raise InvalidChecksum(f"{what} checksum is invalid: {exc}") from exc


def _effective(report: QaReport) -> tuple[str, str]:
    """Identidade do relatório, tolerando modelo contornado (``model_construct``)."""
    render_id = getattr(report, "render_id", None)
    checksum = getattr(report, "checksum", None)
    _require_identity(render_id, checksum, "report")
    return render_id, checksum


def _require_verified_coverage(report: QaReport) -> None:
    coverage = getattr(report, "coverage", None)
    if coverage is None or getattr(coverage, "status", None) != "verified":
        raise CoverageNotVerified(
            "the QA report does not declare a verified coverage; "
            "no executed check is not evidence of quality"
        )
    if not _has_executed_check(getattr(report, "checks_run", ())):
        raise CoverageNotVerified(
            "a verified report requires at least one executed check; "
            "no executed check is not evidence of quality"
        )


def _require_valid_instant(report: QaReport) -> None:
    try:
        _finite_aware_instant(getattr(report, "generated_at", None), "generated_at")
    except ValueError as exc:
        raise InvalidGeneratedAt(str(exc)) from exc


def _require_materialized_collections(report: QaReport) -> None:
    """Exatamente ``tuple``: lista/set/dict/iterador é estado contornado, não cobertura."""
    if type(getattr(report, "findings", None)) is not tuple:
        raise InvalidReportState(
            "report findings must be an exact tuple, not a mutable or single-use collection"
        )
    if type(getattr(report, "checks_run", None)) is not tuple:
        raise InvalidReportState(
            "report checks_run must be an exact tuple, not a mutable or single-use collection"
        )


def _revalidate_report(report: QaReport) -> QaReport:
    """Revalida o estado pelo caminho canônico, cobrindo ``model_copy``/``model_construct``."""
    try:
        payload = report.model_dump()
    except (AttributeError, TypeError, ValueError) as exc:
        raise InvalidReportState(f"QA report state cannot be read: {exc}") from exc
    try:
        return QaReport.model_validate(payload)
    except (ValidationError, TypeError, ValueError) as exc:
        raise InvalidReportState(f"QA report state is not a valid QaReport: {exc}") from exc


def approve(
    *,
    report: QaReport,
    latest: RenderVersion,
    requested: RenderVersion,
) -> RenderVersion:
    """Aprova ``requested`` e devolve a identidade exata que a publicação deve usar.

    Recusa, nesta ordem, cada motivo com um erro próprio:

    1. ``latest``/``requested`` que não sejam ``RenderVersion``
       (``InvalidRenderVersion``);
    2. identidade de render/checksum vazia, com espaço nas bordas ou invisível
       (``InvalidRenderId``/``InvalidChecksum``);
    3. instante de geração inválido (``InvalidGeneratedAt``);
    4. ``findings``/``checks_run`` que não sejam exatamente ``tuple``
       (``InvalidReportState``);
    5. cobertura não verificada ou sem check executado válido
       (``CoverageNotVerified``);
    6. estado restante do relatório que não revalida — revalidado e usado se
       semanticamente equivalente; recusado se não (``InvalidReportState``);
    7. ``requested`` diferente do mais recente (``RenderSuperseded``);
    8. relatório de outro render (``ReportForOtherRender``);
    9. achados ``blocking``, com contagem falha fechada (``BlockingFindings``).

    O retorno é a identidade que o ato de publicar deve reutilizar, sem
    reconsultar "o mais recente" depois — evita aprovar uma versão e publicar
    outra que surgiu no meio do caminho.
    """
    _require_render_version(latest, "latest")
    _require_render_version(requested, "requested")
    _require_identity(latest.render_id, latest.checksum, "latest")
    _require_identity(requested.render_id, requested.checksum, "requested")
    _effective(report)
    _require_valid_instant(report)
    _require_materialized_collections(report)
    _require_verified_coverage(report)
    clean = _revalidate_report(report)

    if requested.render_id != latest.render_id or requested.checksum != latest.checksum:
        raise RenderSuperseded(
            f"render {requested.render_id!r}/{requested.checksum!r} is not the latest "
            f"{latest.render_id!r}/{latest.checksum!r}; re-run QA on the latest render"
        )
    if clean.render_id != requested.render_id or clean.checksum != requested.checksum:
        raise ReportForOtherRender(
            f"QA report covers {clean.render_id!r}/{clean.checksum!r}, "
            f"not the approved render {requested.render_id!r}/{requested.checksum!r}"
        )
    if clean.blocking_findings:
        blockers = ", ".join(sorted({item.check_id for item in clean.blocking_findings}))
        raise BlockingFindings(f"blocking QA findings prevent approval: {blockers}")

    return RenderVersion(render_id=requested.render_id, checksum=requested.checksum)


def assert_publishable(
    *,
    report: QaReport,
    latest: RenderVersion,
    requested: RenderVersion,
) -> None:
    """Igual a ``approve``, mas apenas valida: levanta o erro do motivo, sem retorno."""
    approve(report=report, latest=latest, requested=requested)