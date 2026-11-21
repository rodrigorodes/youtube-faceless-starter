"""Repositório Postgres. Implementa a porta VideoRepository; é o único escritor do schema studio."""
import uuid
from collections.abc import Callable
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from ...application.use_cases import InvalidInput, ServiceUnavailable
from ...domain.contracts import Project, Video, VideoFormat, VideoStatus
from ...domain.qa_report import QaReport
from ...domain.ids import check_id
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


def _video(row: dict) -> Video:
    row = dict(row)
    row["qa_report"] = QaReport.model_validate(row["qa_report"]) if row["qa_report"] else None
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
