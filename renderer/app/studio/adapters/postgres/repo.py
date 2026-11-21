"""Repositório Postgres. Implementa a porta VideoRepository; é o único escritor do schema studio."""
import json
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from pydantic import ValidationError

from ...application.use_cases import InvalidInput, ServiceUnavailable
from ...domain.contracts import Project, Video, VideoFormat, VideoStatus
from ...domain.qa_report import QaCoverage, QaFinding, QaReport
from ...domain.ids import check_id
from ...domain.schema import SCHEMA_VERSION
from ...domain.states import assert_transition


@contextmanager
def _translated():
    """Erros do driver viram erros da aplicação (a API responde 503/422, nunca 500 com stack trace)."""
    try:
        yield
    except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
        raise ServiceUnavailable("studio database unavailable") from exc
    except psycopg.DataError as exc:
        raise InvalidInput("invalid data") from exc


# Marcador explícito da identidade de um relatório legado: NÃO é um render_id/checksum de
# verdade (não casa com o formato 32/64-hex que o gate da F8 exige) — é a declaração de que a
# identidade se perdeu antes da unificação (RP-07b) e não pode ser fabricada.
_LEGACY_QA_IDENTITY = "legacy"
_LEGACY_QA_CHECK = "render.legacy_report"
_LEGACY_QA_FINDING = "legacy-qa-report"
# Instante sentinela: o relatório legado não guardava ``generated_at``. O epoch deixa claro
# que o timestamp também se perdeu — nunca é lido como frescor do relatório.
_LEGACY_QA_INSTANT = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _legacy_qa_report(payload: dict) -> QaReport:
    """Upcast de um ``qa_report`` no shape legado (``passed``/``failures``/``metrics``).

    Linhas gravadas antes da unificação do QA (RP-07b) continuam no formato antigo. Em vez de
    deixar o ``model_validate`` estourar (500 na prévia), a linha é convertida para o contrato
    novo **sem inventar** o que não existia e sem descartar nada:

    - ``coverage`` é ``not_verified``: o relatório não foi produzido pelo avaliador atual, logo
      não pode se declarar ``verified`` (nada executado não é evidência de qualidade).
    - um achado ``info`` registra o fato e preserva o payload legado inteiro (inclusive
      ``metrics``) como evidência — dado algum é perdido em silêncio.
    - ``render_id``/``checksum`` recebem o marcador explícito ``legacy`` (não parece identidade
      de render válida) e ``generated_at`` é o epoch sentinela: identidade e instante se
      perderam e não são fabricados.
    """
    evidence = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return QaReport(
        render_id=_LEGACY_QA_IDENTITY,
        checksum=_LEGACY_QA_IDENTITY,
        generated_at=_LEGACY_QA_INSTANT,
        coverage=QaCoverage(status="not_verified",
                            reason="legacy report from before the QA unification; not verified by the current evaluator"),
        checks_run=(_LEGACY_QA_CHECK,),
        findings=(QaFinding(
            finding_id=_LEGACY_QA_FINDING,
            check_id=_LEGACY_QA_CHECK,
            category="technical",
            severity="info",
            evidence=evidence,
            suggested_action="Re-run the current QA evaluation on this render before publishing.",
        ),),
    )


def _qa_report(payload: dict | None) -> QaReport | None:
    """Valida o ``qa_report`` novo; se for uma linha legada reconhecível, faz o upcast.

    Só o shape legado é tolerado. Um payload novo corrompido continua levantando
    ``ValidationError`` (falha alta): mascarar corrupção do formato atual seria pior.
    """
    if not payload:
        return None
    try:
        return QaReport.model_validate(payload)
    except ValidationError:
        # Só o shape legado na versão conhecida é tolerado. ``schema_version`` desconhecida
        # continua falhando alto (mesma disciplina de ``load_versioned``): não se adivinha a
        # semântica de uma versão futura nem se mascara corrupção do formato atual.
        if (isinstance(payload, dict) and payload.get("schema_version") == SCHEMA_VERSION
                and "passed" in payload and "render_id" not in payload):
            return _legacy_qa_report(payload)
        raise


def _video(row: dict) -> Video:
    row = dict(row)
    row["qa_report"] = _qa_report(row["qa_report"])
    return Video.model_validate(row)


class PostgresVideoRepository:
    def __init__(self, connect: Callable[[], psycopg.Connection]):
        self._connect = connect  # uma conexão por operação: simples e seguro entre threads

    def create_project(self, name: str, niche: str = "", language: str = "pt-BR") -> Project:
        with _translated():
            project_id = uuid.uuid4().hex
            with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute("INSERT INTO studio.projects(id, name, niche, language) VALUES (%s, %s, %s, %s) "
                            "RETURNING id, name, niche, language, budget_usd_month, config, created_at",
                            (project_id, name, niche, language))
                row = cur.fetchone()
            row["budget_usd_month"] = float(row["budget_usd_month"])
            return Project.model_validate(row)

    def get_project(self, project_id: str) -> Project | None:
        with _translated():
            with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT id, name, niche, language, budget_usd_month, config, created_at "
                            "FROM studio.projects WHERE id = %s", (check_id(project_id),))
                row = cur.fetchone()
            if row is None:
                return None
            row["budget_usd_month"] = float(row["budget_usd_month"])
            return Project.model_validate(row)

    def create_video(self, project_id: str, topic: str, fmt: VideoFormat) -> Video:
        with _translated():
            video_id = uuid.uuid4().hex
            with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, %s, %s) "
                            "RETURNING id, project_id, topic, format, status, title, description, tags, privacy, qa_report, schema_version, created_at, updated_at",
                            (video_id, check_id(project_id), topic, fmt.value))
                return _video(cur.fetchone())

    def get_video(self, video_id: str) -> Video | None:
        with _translated():
            with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT id, project_id, topic, format, status, title, description, tags, privacy, qa_report, schema_version, created_at, updated_at "
                            "FROM studio.videos WHERE id = %s", (check_id(video_id),))
                row = cur.fetchone()
            return _video(row) if row else None

    def transition_video(self, video_id: str, expected: VideoStatus, new: VideoStatus) -> bool:
        with _translated():
            assert_transition(expected, new)  # antes de tocar no banco
            with self._connect() as conn:
                cur = conn.execute("UPDATE studio.videos SET status = %s, updated_at = now() WHERE id = %s AND status = %s",
                                   (new.value, check_id(video_id), expected.value))
                return cur.rowcount == 1  # verificar e agir numa operação só
