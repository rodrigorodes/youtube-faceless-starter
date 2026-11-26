"""Repositório Postgres. Implementa a porta VideoRepository; é o único escritor do schema studio."""
import json
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ...application.errors import VisualStyleNotFound
from ...application.use_cases import InvalidInput, ServiceUnavailable
from ...application.video_style import VideoStylePatch, VideoStylePatchConflict
from ...domain.contracts import ProductionMode, Project, Scene, Video, VideoFormat, VideoStatus
from ...domain.qa_report import QaCoverage, QaFinding, QaReport
from ...domain.ids import check_id
from ...domain.schema import SCHEMA_VERSION
from ...domain.states import assert_transition
from ...domain.visual_style import StylePatch


def normalize_style_patch(patch: object) -> dict | None:
    """Normaliza um patch pela allowlist do domínio e devolve o JSONB a gravar (F05.T02).

    Ponto único de persistência do patch, compartilhado pelos repositórios de canal e vídeo: o
    mapping cru passa por ``StylePatch`` (a mesma allowlist da API, com ``StylePatchInvalid``
    apontando a chave) e um patch vazio vira ``None`` — no banco, NULL, "herdar", nunca ``{}``
    com semântica inventada. Puro: não toca o banco.
    """
    typed = patch if isinstance(patch, StylePatch) else StylePatch.from_mapping(patch)
    return typed.to_mapping() or None


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
    if "production_mode" in row and row["production_mode"] is not None:
        row["production_mode"] = ProductionMode(row["production_mode"])
    return Video.model_validate(row)


def _video_style_patch(row: dict) -> VideoStylePatch:
    return VideoStylePatch(revision=row["style_patch_revision"], patch=row["style_patch"])


def _scene_from_row(row: dict) -> Scene:
    """Carrega Scene a partir de um dict row de studio.scenes."""
    return Scene(
        id=row["id"],
        video_id=row["video_id"],
        idx=row["idx"],
        narration=row["narration"],
        caption=row.get("caption", ""),
        label=row.get("label", ""),
        image_prompt=row["image_prompt"],
        claim_ids=row.get("claim_ids") or [],
        asset_id=row.get("asset_id"),
        duration_s=row.get("duration_s"),
        broll_enabled=bool(row.get("broll_enabled", False)),
        broll_note=row.get("broll_note"),
        visual_intent=row.get("visual_intent") or "",
        search_queries=row.get("search_queries") or [],
    )


def _load_scenes(conn, video_id: str) -> list[Scene]:
    """Carrega cenas de um vídeo a partir de studio.scenes."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, video_id, idx, narration, caption, label, image_prompt, claim_ids, "
            "asset_id, duration_s, broll_enabled, broll_note, visual_intent, search_queries "
            "FROM studio.scenes WHERE video_id = %s ORDER BY idx",
            (check_id(video_id),),
        )
        return [_scene_from_row(row) for row in cur.fetchall()]


def save_scenes(conn, video_id: str, scenes: list[Scene]) -> None:
    """Persiste cenas em studio.scenes incluindo broll_enabled e broll_note."""
    vid = check_id(video_id)
    with conn.cursor() as cur:
        for s in scenes:
            cur.execute(
                "INSERT INTO studio.scenes (id, video_id, idx, narration, caption, label, "
                "image_prompt, claim_ids, asset_id, duration_s, broll_enabled, broll_note, visual_intent, search_queries) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET "
                "idx = EXCLUDED.idx, narration = EXCLUDED.narration, caption = EXCLUDED.caption, "
                "label = EXCLUDED.label, image_prompt = EXCLUDED.image_prompt, "
                "claim_ids = EXCLUDED.claim_ids, asset_id = EXCLUDED.asset_id, "
                "duration_s = EXCLUDED.duration_s, broll_enabled = EXCLUDED.broll_enabled, "
                "broll_note = EXCLUDED.broll_note, visual_intent = EXCLUDED.visual_intent, "
                "search_queries = EXCLUDED.search_queries",
                (
                    s.id,
                    vid,
                    s.idx,
                    s.narration,
                    s.caption,
                    s.label,
                    s.image_prompt,
                    Jsonb(s.claim_ids),
                    s.asset_id,
                    s.duration_s,
                    s.broll_enabled,
                    s.broll_note,
                    getattr(s, "visual_intent", "") or "",
                    Jsonb(getattr(s, "search_queries", []) or []),
                ),
            )


def replace_scenes(conn, video_id: str, scenes: list[Scene]) -> None:
    """Substitui cenas de um vídeo em studio.scenes."""
    vid = check_id(video_id)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM studio.scenes WHERE video_id = %s", (vid,))
    save_scenes(conn, vid, scenes)


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

    def set_project_config(self, project_id: str, config: dict[str, str]) -> Project | None:
        with _translated():
            with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute("UPDATE studio.projects SET config = %s WHERE id = %s "
                            "RETURNING id, name, niche, language, budget_usd_month, config, created_at",
                            (Jsonb(config), check_id(project_id)))
                row = cur.fetchone()
            if row is None:
                return None
            row["budget_usd_month"] = float(row["budget_usd_month"])
            return Project.model_validate(row)

    def create_video(self, project_id: str, topic: str, fmt: VideoFormat,
                     style_id: str | None = None,
                     production_mode: ProductionMode = ProductionMode.piloto,
                     target_duration_s: int | None = None,
                     pacing_preset: str = "dynamic",
                     budget_cap_usd: float | None = None) -> Video:
        """Cria o vídeo já com o estilo escolhido (F02.T02), numa única transação.

        O estilo é validado no caso de uso (existe e está ativo); a FK do banco é a última
        barreira contra um vínculo quebrado.
        """
        with _translated():
            video_id = uuid.uuid4().hex
            sid = check_id(style_id) if style_id is not None else None
            pmode = production_mode.value if isinstance(production_mode, ProductionMode) else str(production_mode)
            with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                try:
                    cur.execute("INSERT INTO studio.videos(id, project_id, topic, format, style_id, production_mode, target_duration_s, pacing_preset, budget_cap_usd) "
                                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                                "RETURNING id, project_id, topic, format, status, production_mode, title, description, tags, privacy, style_id, qa_report, schema_version, target_duration_s, pacing_preset, budget_cap_usd, creative_brief, created_at, updated_at",
                                (video_id, check_id(project_id), topic, fmt.value, sid, pmode, target_duration_s, pacing_preset, budget_cap_usd))
                except psycopg.errors.ForeignKeyViolation as exc:
                    # corrida com o arquivamento entre a validação e o INSERT: falha fechado,
                    # sem deixar vídeo com vínculo quebrado
                    raise VisualStyleNotFound(f"visual style {style_id!r} does not exist") from exc
                return _video(cur.fetchone())

    def get_video(self, video_id: str) -> Video | None:
        with _translated():
            with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT id, project_id, topic, format, status, production_mode, title, description, tags, privacy, style_id, qa_report, schema_version, target_duration_s, pacing_preset, budget_cap_usd, creative_brief, created_at, updated_at "
                            "FROM studio.videos WHERE id = %s", (check_id(video_id),))
                row = cur.fetchone()
            return _video(row) if row else None

    def list_by_project(self, project_id: str) -> list[Video]:
        with _translated():
            with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT id, project_id, topic, format, status, production_mode, title, description, tags, privacy, style_id, qa_report, schema_version, target_duration_s, pacing_preset, budget_cap_usd, creative_brief, created_at, updated_at "
                            "FROM studio.videos WHERE project_id = %s ORDER BY created_at", (check_id(project_id),))
                return [_video(r) for r in cur.fetchall()]

    def update_video_creative_brief(self, video_id: str, brief_dict: dict) -> None:
        with _translated():
            with self._connect() as conn, conn.transaction(), conn.cursor() as cur:
                cur.execute("UPDATE studio.videos SET creative_brief = %s, updated_at = NOW() WHERE id = %s",
                            (psycopg.types.json.Jsonb(brief_dict), check_id(video_id)))

    def update_video_pacing_preset(self, video_id: str, preset: str) -> None:
        with _translated():
            with self._connect() as conn, conn.transaction(), conn.cursor() as cur:
                cur.execute("UPDATE studio.videos SET pacing_preset = %s, updated_at = NOW() WHERE id = %s",
                            (preset, check_id(video_id)))

    def get_video_style_patch(self, video_id: str) -> VideoStylePatch | None:
        """Lê o override de estilo do vídeo (F05.T02); ``None`` se o vídeo não existe.

        Sem patch, devolve ``VideoStylePatch(revision=0, patch=None)``: o vídeo herda. A leitura é
        escopada por vídeo — o patch de um vídeo nunca aparece em outro.
        """
        with _translated():
            with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT style_patch, style_patch_revision FROM studio.videos WHERE id = %s",
                            (check_id(video_id),))
                row = cur.fetchone()
            return _video_style_patch(row) if row else None

    def set_video_style_patch(self, video_id: str, expected_revision: int,
                              patch: object) -> VideoStylePatch | None:
        """Grava (ou remove, com None) o override tipado do vídeo, com controle otimista.

        O patch é normalizado pela allowlist do domínio antes do UPDATE (``StylePatchInvalid``
        sobe sem gravar) e um patch vazio vira NULL: reset **remove** o patch, o vídeo volta a
        herdar do canal. ``expected_revision`` divergente é ``VideoStylePatchConflict`` — a
        comparação e a escrita acontecem sob o mesmo ``SELECT ... FOR UPDATE`` (uma operação só).
        """
        vid = check_id(video_id)
        stored = normalize_style_patch(patch)  # StylePatchInvalid antes de qualquer SQL
        with _translated():
            with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT style_patch_revision FROM studio.videos WHERE id = %s FOR UPDATE",
                            (vid,))
                row = cur.fetchone()
                if row is None:
                    return None
                current = row["style_patch_revision"]
                if current != expected_revision:
                    raise VideoStylePatchConflict(
                        f"expected style patch revision {expected_revision}, found {current}")
                cur.execute(
                    "UPDATE studio.videos SET style_patch = %s, "
                    "style_patch_revision = style_patch_revision + 1, updated_at = now() "
                    "WHERE id = %s RETURNING style_patch, style_patch_revision",
                    (Jsonb(stored) if stored is not None else None, vid),
                )
                return _video_style_patch(cur.fetchone())

    def transition_video(self, video_id: str, expected: VideoStatus, new: VideoStatus) -> bool:
        with _translated():
            assert_transition(expected, new)  # antes de tocar no banco
            with self._connect() as conn:
                cur = conn.execute("UPDATE studio.videos SET status = %s, updated_at = now() WHERE id = %s AND status = %s",
                                   (new.value, check_id(video_id), expected.value))
                return cur.rowcount == 1  # verificar e agir numa operação só

    def set_video_style(self, video_id: str, style_id: str | None) -> Video | None:
        """VS-02b: fixa (ou limpa, com None) o estilo que **sobrepõe** o do canal neste vídeo.

        Devolve None se o vídeo não existe; `VisualStyleNotFound` se o estilo não existe (a FK
        recusa apontar para um estilo inexistente — nunca fica um vínculo quebrado).
        """
        with _translated():
            with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
                try:
                    cur.execute(
                        "UPDATE studio.videos SET style_id = %s, updated_at = now() WHERE id = %s "
                        "RETURNING id, project_id, topic, format, status, production_mode, title, description, tags, privacy, style_id, qa_report, schema_version, created_at, updated_at",
                        (check_id(style_id) if style_id is not None else None, check_id(video_id)))
                except psycopg.errors.ForeignKeyViolation as exc:
                    raise VisualStyleNotFound(f"visual style {style_id!r} does not exist") from exc
                row = cur.fetchone()
            return _video(row) if row else None

    def load_scenes(self, video_id: str) -> list[Scene]:
        with _translated(), self._connect() as conn:
            return _load_scenes(conn, video_id)

    def save_scenes(self, video_id: str, scenes: list[Scene]) -> None:
        with _translated(), self._connect() as conn:
            save_scenes(conn, video_id, scenes)

    def replace_scenes(self, video_id: str, scenes: list[Scene]) -> None:
        with _translated(), self._connect() as conn:
            replace_scenes(conn, video_id, scenes)
