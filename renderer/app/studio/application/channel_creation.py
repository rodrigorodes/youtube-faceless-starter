"""Caso de uso transacional de criação de canal completo (Task 5).

Cria atomicamente em uma única transação de banco:
- Projeto em studio.projects
- Perfil em studio.channel_profiles e snapshot em studio.channel_profile_revisions
- Orçamento em studio.channel_budgets
- Configuração opcional de provedor em studio.projects.config
- Registro de idempotência em studio.channel_creation_requests
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import dataclasses
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import importlib
import json
from typing import Any, Callable
import uuid

from ..domain.channel import ChannelProfile, ChannelStyleNotFound
from ..domain.channel_budget import BudgetLimitInvalid, BudgetLimits
from ..domain.contracts import ProductionMode, Project, VideoFormat
from ..domain.production_run import canonical_idempotency_key
from ..domain.provider import EconomicProfile
from .errors import InvalidInput, ServiceUnavailable


class IdempotencyConflict(ValueError):
    """A chave de idempotência já foi usada com um payload divergente."""


def _psycopg():
    return importlib.import_module("psycopg")


def _dict_row():
    return importlib.import_module("psycopg.rows").dict_row


def _jsonb(val: object):
    return importlib.import_module("psycopg.types.json").Jsonb(val)


@contextmanager
def _translated():
    psycopg = _psycopg()
    try:
        yield
    except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
        raise ServiceUnavailable("studio database unavailable") from exc
    except psycopg.DataError as exc:
        raise InvalidInput("invalid data") from exc


_CHANNEL_PROFILE_COLS = (
    "id, project_id, name, strategy, language, audience, pillars, narrative, target_duration_s, "
    "visual_identity, voice, audio, thumbnail, cta, style_id, style_patch, style_patch_revision, "
    "youtube_channel_id, default_mode, default_format, version, archived, created_at, updated_at, voice_settings"
)


def _profile_from_row(row: dict) -> ChannelProfile:
    r = dict(row)
    r["pillars"] = tuple(r["pillars"]) if r.get("pillars") is not None else ()
    r["voice_settings"] = dict(r.get("voice_settings") or {})
    if "default_mode" in r and r["default_mode"] is not None:
        r["default_mode"] = ProductionMode(r["default_mode"])
    if "default_format" in r and r["default_format"] is not None:
        r["default_format"] = VideoFormat(r["default_format"])
    return ChannelProfile(**r)


def _snapshot(profile: ChannelProfile) -> dict[str, object]:
    snapshot: dict[str, object] = {}
    for field in dataclasses.fields(profile):
        value = getattr(profile, field.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, tuple):
            value = list(value)
        elif isinstance(value, Mapping):
            value = dict(value)
        elif hasattr(value, "to_mapping"):
            value = value.to_mapping()
        elif isinstance(value, (ProductionMode, VideoFormat)):
            value = value.value
        snapshot[field.name] = value
    return snapshot


@dataclass(frozen=True)
class ChannelCreationPayload:
    # Project fields
    name: str
    niche: str = ""
    language: str = "pt-BR"
    # Channel profile fields
    strategy: str = ""
    audience: str = ""
    pillars: tuple[str, ...] = ()
    narrative: str = ""
    target_duration_s: int = 60
    visual_identity: str = ""
    voice: str = ""
    voice_settings: dict[str, object] = dataclasses.field(default_factory=dict)
    audio: str = ""
    thumbnail: str = ""
    cta: str = ""
    style_id: str | None = None
    youtube_channel_id: str | None = None
    default_mode: ProductionMode = ProductionMode.piloto
    default_format: VideoFormat = VideoFormat.short
    # Budget limits
    hard_monthly_usd: float | Decimal = 100.0
    soft_monthly_usd: float | Decimal | None = None
    hard_video_usd: float | Decimal = 10.0
    soft_video_usd: float | Decimal | None = None
    economic_profile: EconomicProfile = EconomicProfile.BALANCED
    # Optional provider config
    provider_config: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.pillars, (list, tuple)):
            object.__setattr__(
                self,
                "pillars",
                tuple(str(p).strip() for p in self.pillars if str(p).strip()),
            )
        if isinstance(self.default_mode, str):
            object.__setattr__(self, "default_mode", ProductionMode(self.default_mode))
        if isinstance(self.default_format, str):
            object.__setattr__(self, "default_format", VideoFormat(self.default_format))
        if isinstance(self.economic_profile, str):
            object.__setattr__(self, "economic_profile", EconomicProfile(self.economic_profile))

        # Soft defaults based on hard
        if self.soft_monthly_usd is None:
            if self.hard_monthly_usd < 80.0:
                object.__setattr__(self, "soft_monthly_usd", self.hard_monthly_usd)
            else:
                object.__setattr__(
                    self,
                    "soft_monthly_usd",
                    80.0 if self.hard_monthly_usd == 100.0 else self.hard_monthly_usd,
                )
        if self.soft_video_usd is None:
            if self.hard_video_usd < 8.0:
                object.__setattr__(self, "soft_video_usd", self.hard_video_usd)
            else:
                object.__setattr__(
                    self,
                    "soft_video_usd",
                    8.0 if self.hard_video_usd == 10.0 else self.hard_video_usd,
                )


@dataclass(frozen=True)
class TransactionalChannelResult:
    project: Project
    profile: ChannelProfile
    budget: BudgetLimits


def _format_money(val: float | Decimal | int | None) -> str:
    if val is None:
        return "0.00"
    return f"{float(val):.2f}"


def _canonical_payload_dict(payload: ChannelCreationPayload) -> dict[str, object]:
    return {
        "name": payload.name,
        "niche": payload.niche,
        "language": payload.language,
        "strategy": payload.strategy,
        "audience": payload.audience,
        "pillars": list(payload.pillars),
        "narrative": payload.narrative,
        "target_duration_s": payload.target_duration_s,
        "visual_identity": payload.visual_identity,
        "voice": payload.voice,
        "audio": payload.audio,
        "thumbnail": payload.thumbnail,
        "cta": payload.cta,
        "style_id": payload.style_id,
        "youtube_channel_id": payload.youtube_channel_id,
        "default_mode": (
            payload.default_mode.value
            if isinstance(payload.default_mode, ProductionMode)
            else str(payload.default_mode)
        ),
        "default_format": (
            payload.default_format.value
            if isinstance(payload.default_format, VideoFormat)
            else str(payload.default_format)
        ),
        "hard_monthly_usd": _format_money(payload.hard_monthly_usd),
        "soft_monthly_usd": _format_money(payload.soft_monthly_usd),
        "hard_video_usd": _format_money(payload.hard_video_usd),
        "soft_video_usd": _format_money(payload.soft_video_usd),
        "economic_profile": (
            payload.economic_profile.value
            if isinstance(payload.economic_profile, EconomicProfile)
            else str(payload.economic_profile)
        ),
        "provider_config": (
            dict(sorted(payload.provider_config.items())) if payload.provider_config else {}
        ),
    }


def _payload_hash(payload: ChannelCreationPayload) -> str:
    canonical = json.dumps(
        _canonical_payload_dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CreateChannelTransactional:
    def __init__(self, connect: Callable[[], Any]):
        self._connect = connect

    def execute(
        self,
        payload: ChannelCreationPayload,
        idempotency_key: str | None = None,
    ) -> TransactionalChannelResult:
        if not isinstance(payload, ChannelCreationPayload):
            raise ValueError("payload must be a ChannelCreationPayload")

        # Validate budget limits before SQL
        BudgetLimits(
            project_id=uuid.uuid4().hex,
            hard_monthly_usd=Decimal(str(payload.hard_monthly_usd)),
            soft_monthly_usd=Decimal(str(payload.soft_monthly_usd)),
            hard_video_usd=Decimal(str(payload.hard_video_usd)),
            soft_video_usd=Decimal(str(payload.soft_video_usd)),
            economic_profile=payload.economic_profile,
        )

        canonical_key: str | None = None
        payload_hash: str | None = None
        if idempotency_key is not None:
            canonical_key = canonical_idempotency_key(idempotency_key)
            payload_hash = _payload_hash(payload)

        psycopg = _psycopg()
        try:
            with _translated(), self._connect() as conn:
                try:
                    with conn.transaction():
                        with conn.cursor(row_factory=_dict_row()) as cur:
                            if canonical_key is not None:
                                cur.execute(
                                    "SELECT project_id, request_hash FROM studio.channel_creation_requests WHERE idempotency_key = %s FOR UPDATE",
                                    (canonical_key,),
                                )
                                existing = cur.fetchone()
                                if existing is not None:
                                    if existing["request_hash"] != payload_hash:
                                        raise IdempotencyConflict(
                                            "Idempotency key already used with different payload"
                                        )
                                    return self._load_channel(cur, existing["project_id"])

                            # 1. Insert into studio.projects
                            project_id = uuid.uuid4().hex
                            cur.execute(
                                """INSERT INTO studio.projects (id, name, niche, language)
                                VALUES (%s, %s, %s, %s)
                                RETURNING id, name, niche, language, budget_usd_month, config, created_at""",
                                (project_id, payload.name, payload.niche, payload.language),
                            )
                            project_row = cur.fetchone()

                            # 2. Insert into studio.channel_profiles & snapshot into studio.channel_profile_revisions
                            profile_id = uuid.uuid4().hex
                            profile_to_create = ChannelProfile(
                                id=profile_id,
                                project_id=project_id,
                                name=payload.name,
                                strategy=payload.strategy,
                                language=payload.language,
                                audience=payload.audience,
                                pillars=payload.pillars,
                                narrative=payload.narrative,
                                target_duration_s=payload.target_duration_s,
                                visual_identity=payload.visual_identity,
                                voice=payload.voice,
                                voice_settings=payload.voice_settings,
                                audio=payload.audio,
                                thumbnail=payload.thumbnail,
                                cta=payload.cta,
                                style_id=payload.style_id,
                                youtube_channel_id=payload.youtube_channel_id,
                                default_mode=payload.default_mode,
                                default_format=payload.default_format,
                            )
                            cur.execute(
                                f"""INSERT INTO studio.channel_profiles (
                                    id, project_id, name, strategy, language, audience, pillars, narrative, target_duration_s,
                                    visual_identity, voice, audio, thumbnail, cta, style_id, youtube_channel_id,
                                    default_mode, default_format, version, archived, voice_settings
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                RETURNING {_CHANNEL_PROFILE_COLS}""",
                                (
                                    profile_to_create.id,
                                    profile_to_create.project_id,
                                    profile_to_create.name,
                                    profile_to_create.strategy,
                                    profile_to_create.language,
                                    profile_to_create.audience,
                                    list(profile_to_create.pillars),
                                    profile_to_create.narrative,
                                    profile_to_create.target_duration_s,
                                    profile_to_create.visual_identity,
                                    profile_to_create.voice,
                                    profile_to_create.audio,
                                    profile_to_create.thumbnail,
                                    profile_to_create.cta,
                                    profile_to_create.style_id,
                                    profile_to_create.youtube_channel_id,
                                    profile_to_create.default_mode.value,
                                    profile_to_create.default_format.value,
                                    profile_to_create.version,
                                    profile_to_create.archived,
                                    _jsonb(dict(profile_to_create.voice_settings)),
                                ),
                            )
                            profile_row = cur.fetchone()
                            created_profile = _profile_from_row(profile_row)

                            cur.execute(
                                "INSERT INTO studio.channel_profile_revisions (profile_id, version, snapshot) VALUES (%s, %s, %s)",
                                (created_profile.id, created_profile.version, _jsonb(_snapshot(created_profile))),
                            )

                            # 3. Insert into studio.channel_budgets
                            cur.execute(
                                """INSERT INTO studio.channel_budgets (
                                    project_id, hard_monthly_usd, soft_monthly_usd, hard_video_usd, soft_video_usd, economic_profile
                                ) VALUES (%s, %s, %s, %s, %s, %s)
                                RETURNING project_id, hard_monthly_usd, soft_monthly_usd, hard_video_usd, soft_video_usd, economic_profile, updated_at""",
                                (
                                    project_id,
                                    Decimal(str(payload.hard_monthly_usd)),
                                    Decimal(str(payload.soft_monthly_usd)),
                                    Decimal(str(payload.hard_video_usd)),
                                    Decimal(str(payload.soft_video_usd)),
                                    payload.economic_profile.value,
                                ),
                            )
                            budget_row = cur.fetchone()
                            created_budget = BudgetLimits(
                                project_id=project_id,
                                hard_monthly_usd=budget_row["hard_monthly_usd"],
                                soft_monthly_usd=budget_row["soft_monthly_usd"],
                                hard_video_usd=budget_row["hard_video_usd"],
                                soft_video_usd=budget_row["soft_video_usd"],
                                economic_profile=EconomicProfile(budget_row["economic_profile"]),
                                updated_at=budget_row["updated_at"],
                            )

                            # 4. If provider_config: update config in studio.projects
                            if payload.provider_config:
                                cur.execute(
                                    """UPDATE studio.projects
                                    SET config = %s
                                    WHERE id = %s
                                    RETURNING id, name, niche, language, budget_usd_month, config, created_at""",
                                    (_jsonb(payload.provider_config), project_id),
                                )
                                project_row = cur.fetchone()

                            project_row["budget_usd_month"] = float(project_row["budget_usd_month"])
                            created_project = Project.model_validate(project_row)

                            # 5. If idempotency_key: insert into studio.channel_creation_requests
                            if canonical_key is not None and payload_hash is not None:
                                cur.execute(
                                    """INSERT INTO studio.channel_creation_requests (idempotency_key, project_id, request_hash)
                                    VALUES (%s, %s, %s)""",
                                    (canonical_key, project_id, payload_hash),
                                )

                            return TransactionalChannelResult(
                                project=created_project,
                                profile=created_profile,
                                budget=created_budget,
                            )
                except psycopg.errors.UniqueViolation:
                    if canonical_key is not None:
                        with conn.transaction():
                            with conn.cursor(row_factory=_dict_row()) as cur:
                                cur.execute(
                                    "SELECT project_id, request_hash FROM studio.channel_creation_requests WHERE idempotency_key = %s",
                                    (canonical_key,),
                                )
                                existing = cur.fetchone()
                                if existing is not None:
                                    if existing["request_hash"] != payload_hash:
                                        raise IdempotencyConflict(
                                            "Idempotency key already used with different payload"
                                        )
                                    return self._load_channel(cur, existing["project_id"])
                    raise
        except psycopg.errors.CheckViolation as exc:
            raise BudgetLimitInvalid("database rejected the budget limits") from exc
        except psycopg.errors.ForeignKeyViolation as exc:
            if payload.style_id is not None:
                raise ChannelStyleNotFound(f"visual style {payload.style_id!r} does not exist") from exc
            raise

    def _load_channel(self, cur, project_id: str) -> TransactionalChannelResult:
        cur.execute(
            """SELECT id, name, niche, language, budget_usd_month, config, created_at
            FROM studio.projects WHERE id = %s""",
            (project_id,),
        )
        p_row = cur.fetchone()
        if p_row is None:
            raise RuntimeError(f"Project '{project_id}' not found for existing channel creation request")
        p_row["budget_usd_month"] = float(p_row["budget_usd_month"])
        project = Project.model_validate(p_row)

        cur.execute(
            f"SELECT {_CHANNEL_PROFILE_COLS} FROM studio.channel_profiles WHERE project_id = %s",
            (project_id,),
        )
        prof_row = cur.fetchone()
        if prof_row is None:
            raise RuntimeError(f"Channel profile not found for project '{project_id}'")
        profile = _profile_from_row(prof_row)

        cur.execute(
            """SELECT project_id, hard_monthly_usd, soft_monthly_usd, hard_video_usd, soft_video_usd, economic_profile, updated_at
            FROM studio.channel_budgets WHERE project_id = %s""",
            (project_id,),
        )
        b_row = cur.fetchone()
        if b_row is None:
            raise RuntimeError(f"Channel budget not found for project '{project_id}'")
        budget = BudgetLimits(
            project_id=project_id,
            hard_monthly_usd=b_row["hard_monthly_usd"],
            soft_monthly_usd=b_row["soft_monthly_usd"],
            hard_video_usd=b_row["hard_video_usd"],
            soft_video_usd=b_row["soft_video_usd"],
            economic_profile=EconomicProfile(b_row["economic_profile"]),
            updated_at=b_row["updated_at"],
        )

        return TransactionalChannelResult(project=project, profile=profile, budget=budget)
