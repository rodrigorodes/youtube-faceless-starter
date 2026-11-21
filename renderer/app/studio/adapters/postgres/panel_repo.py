"""Repositório de leitura agregada para o painel do Studio (Postgres)."""
from datetime import datetime

from psycopg.rows import dict_row

from ...application.ports import (
    LatestRun,
    PanelRepository,
    PubInfo,
    SourceInfo,
    StepInfo,
    UsageInfo,
    VideoDetail,
    VideoRow,
)
from ...domain.contracts import JobStatus, PublicationStatus, VideoFormat, VideoStatus
from ...domain.ids import check_id
from .editorial_repo import _Base
from .repo import _translated


class PostgresPanelRepository(_Base):
    def projects(self) -> list[tuple[str, str]]:
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, name FROM studio.projects ORDER BY created_at, id")
            return [(r[0], r[1]) for r in cur.fetchall()]

    def videos(self, since: datetime | None, project_id: str | None, limit: int) -> list[VideoRow]:
        clauses = []
        params: list[object] = []
        if since is not None:
            clauses.append("v.updated_at >= %s")
            params.append(since)
        if project_id is not None:
            clauses.append("v.project_id = %s")
            params.append(check_id(project_id))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        query = f"""
            SELECT
                v.id, v.project_id, v.topic, v.format, v.status, v.title, v.updated_at,
                j.status AS job_status,
                left(j.error, 300) AS render_error,
                EXISTS(SELECT 1 FROM studio.step_runs sr WHERE sr.video_id = v.id AND sr.status = 'RUNNING') AS step_running,
                p.status AS publication_status,
                left(p.error, 300) AS pub_error,
                COALESCE(
                    (SELECT jsonb_agg(jsonb_build_array(u.provider, u.model, u.cost_usd, u.cost_confirmation_kind) ORDER BY u.id)
                     FROM studio.usage_ledger u WHERE u.video_id = v.id),
                    '[]'::jsonb
                ) AS costs
            FROM studio.videos v
            LEFT JOIN LATERAL (
                SELECT status, error FROM studio.render_jobs r
                WHERE r.video_id = v.id
                ORDER BY r.created_at DESC, r.attempt DESC, r.id DESC
                LIMIT 1
            ) j ON true
            LEFT JOIN studio.publications p ON p.video_id = v.id
            {where}
            ORDER BY v.updated_at DESC, v.id DESC
            LIMIT %s
        """
        params.append(max(1, min(limit, 1000)))

        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

        out: list[VideoRow] = []
        for r in rows:
            costs = [(item[0], item[1], float(item[2]), item[3]) for item in (r["costs"] or [])]
            err = r["pub_error"] or r["render_error"]
            out.append(VideoRow(
                id=r["id"],
                project_id=r["project_id"],
                topic=r["topic"],
                format=VideoFormat(r["format"]),
                status=VideoStatus(r["status"]),
                title=r["title"],
                updated_at=r["updated_at"],
                job_status=JobStatus(r["job_status"]) if r["job_status"] else None,
                step_running=bool(r["step_running"]),
                publication_status=PublicationStatus(r["publication_status"]) if r["publication_status"] else None,
                error=err,
                cost_rows=costs,
            ))
        return out

    def video_detail(self, video_id: str) -> VideoDetail | None:
        v_id = check_id(video_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            # 1. Video Row
            cur.execute("""
                SELECT
                    v.id, v.project_id, v.topic, v.format, v.status, v.title, v.updated_at,
                    j.status AS job_status,
                    left(j.error, 300) AS render_error,
                    EXISTS(SELECT 1 FROM studio.step_runs sr WHERE sr.video_id = v.id AND sr.status = 'RUNNING') AS step_running,
                    p.status AS publication_status,
                    p.attempt AS publication_attempt,
                    left(p.error, 300) AS pub_error
                FROM studio.videos v
                LEFT JOIN LATERAL (
                    SELECT status, error FROM studio.render_jobs r
                    WHERE r.video_id = v.id
                    ORDER BY r.created_at DESC, r.attempt DESC, r.id DESC
                    LIMIT 1
                ) j ON true
                LEFT JOIN studio.publications p ON p.video_id = v.id
                WHERE v.id = %s
            """, (v_id,))
            vr = cur.fetchone()
            if vr is None:
                return None

            # 2. Steps
            cur.execute("""
                SELECT step, attempt, status, error_class, left(error_message, 300) AS error_message, started_at, finished_at
                FROM studio.step_runs
                WHERE video_id = %s
                ORDER BY started_at, attempt
            """, (v_id,))
            step_rows = cur.fetchall()

            # 3. Usage
            cur.execute("""
                SELECT step, provider, model, cost_usd, cost_confirmation_kind, created_at
                FROM studio.usage_ledger
                WHERE video_id = %s
                ORDER BY id
            """, (v_id,))
            usage_rows = cur.fetchall()

            # 4. Fontes registradas (sem o texto: a página só lista URL e tamanho)
            cur.execute("""
                SELECT id, url, length(text) AS chars
                FROM studio.source_snapshots
                WHERE video_id = %s
                ORDER BY fetched_at, id
            """, (v_id,))
            source_rows = cur.fetchall()

            # 5. Execução de produção mais recente + a etapa que falhou (motivo real do servidor)
            cur.execute("""
                SELECT pr.run_id, pr.state, fs.stage_id AS failed_stage, fs.error AS failure_reason
                FROM studio.production_runs pr
                LEFT JOIN LATERAL (
                    SELECT stage_id, error FROM studio.stage_executions se
                    WHERE se.run_id = pr.run_id AND se.state = 'FAILED'
                    ORDER BY se.updated_at DESC, se.stage_id
                    LIMIT 1
                ) fs ON true
                WHERE pr.video_id = %s
                ORDER BY pr.created_at DESC, pr.run_id DESC
                LIMIT 1
            """, (v_id,))
            run_row = cur.fetchone()

        costs = [(u["provider"], u["model"], float(u["cost_usd"]), u["cost_confirmation_kind"]) for u in usage_rows]
        video_row = VideoRow(
            id=vr["id"],
            project_id=vr["project_id"],
            topic=vr["topic"],
            format=VideoFormat(vr["format"]),
            status=VideoStatus(vr["status"]),
            title=vr["title"],
            updated_at=vr["updated_at"],
            job_status=JobStatus(vr["job_status"]) if vr["job_status"] else None,
            step_running=bool(vr["step_running"]),
            publication_status=PublicationStatus(vr["publication_status"]) if vr["publication_status"] else None,
            error=vr["pub_error"] or vr["render_error"],
            cost_rows=costs,
        )

        steps = [
            StepInfo(
                step=s["step"],
                attempt=s["attempt"],
                status=s["status"],
                error_class=s["error_class"],
                error_message=s["error_message"],
                started_at=s["started_at"],
                finished_at=s["finished_at"],
            )
            for s in step_rows
        ]

        usage = [
            UsageInfo(
                step=u["step"],
                provider=u["provider"],
                model=u["model"],
                cost_usd=float(u["cost_usd"]),
                created_at=u["created_at"],
                cost_confirmation_kind=u["cost_confirmation_kind"],
            )
            for u in usage_rows
        ]

        pub = None
        if vr["publication_status"]:
            pub = PubInfo(
                status=PublicationStatus(vr["publication_status"]),
                attempt=vr["publication_attempt"] or 1,
                error=vr["pub_error"],
            )

        sources = [
            SourceInfo(id=s["id"], url=s["url"], chars=int(s["chars"]))
            for s in source_rows
        ]

        latest_run = None
        if run_row is not None:
            reason = run_row["failure_reason"]
            latest_run = LatestRun(
                run_id=run_row["run_id"],
                state=run_row["state"],
                failed_stage=run_row["failed_stage"],
                failure_reason=reason[:500] if reason else None,
            )

        return VideoDetail(
            video=video_row,
            steps=steps,
            usage=usage,
            render_error=vr["render_error"],
            publication=pub,
            sources=sources,
            latest_run=latest_run,
        )

    def month_usage(self) -> list[tuple[str, str, float, str | None]]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT provider, model, cost_usd, cost_confirmation_kind
                FROM studio.usage_ledger
                WHERE created_at >= date_trunc('month', now())
                ORDER BY id
            """)
            rows = cur.fetchall()
        return [
            (r["provider"], r["model"], float(r["cost_usd"]), r["cost_confirmation_kind"])
            for r in rows
        ]

    def unattributed_usage(self) -> list[tuple[str, str, float]]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT provider, model, cost_usd
                FROM studio.usage_ledger
                WHERE video_id IS NULL AND created_at >= date_trunc('month', now())
                ORDER BY id
            """)
            return [(r["provider"], r["model"], float(r["cost_usd"])) for r in cur.fetchall()]
