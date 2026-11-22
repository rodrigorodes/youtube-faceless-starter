"""Settings da raiz de composição: configuração tipada e leitura do ambiente."""
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..application.production import ProductionMode


DEFAULT_ALLOWLIST = ("amsterdam-dance-event.nl",)
DEFAULT_ALLOW_NAMES = ("amsterda",)  # exônimo pt-BR de Amsterdam


def _csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    items = tuple(x.strip().lower() for x in (value or "").split(",") if x.strip())
    return items or default


def _cap(value: str | None, default: float) -> float:
    try:
        number = float(value) if value not in (None, "") else default
    except ValueError:
        return default
    return number if number == number and 0 <= number < float("inf") else default


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _production_mode(value: str | None) -> ProductionMode:
    try:
        return ProductionMode((value or ProductionMode.INTERACTIVE.value).strip().upper())
    except ValueError:
        return ProductionMode.INTERACTIVE


@dataclass(frozen=True)
class Settings:
    database_url: str | None = None
    storage_root: Path = Path("/data")
    source_allowlist: tuple[str, ...] = DEFAULT_ALLOWLIST
    allow_names: tuple[str, ...] = DEFAULT_ALLOW_NAMES
    max_cost_video: float = 0.0   # gasto pago só com o teto do vídeo liberado explicitamente
    max_cost_month: float = 15.0  # teto mensal do projeto (US$ 15)
    bridge_token: str = ""
    bridge_url: str = "http://host.docker.internal:8787"
    pexels_key: str = ""
    paid_image_usd: float = 0.05        # estimativa por imagem de modelo não ':free' (o guard decide)
    veo_usd_per_second: float = 0.40    # Veo 3.1 (conferido em out/2026); clipe de 8 s
    render_concurrency: int = 1         # renders simultâneos (1 não satura o Lenovo)
    trend_hosts: tuple[str, ...] = ("www.googleapis.com", "www.youtube.com")
    token_env_path: Path = Path("credentials/token.env")
    budget_guard: bool = False  # liga a reserva preventiva de orçamento nos caminhos pagos (STUDIO_BUDGET_GUARD=1)
    production_mode: ProductionMode = ProductionMode.INTERACTIVE  # modo do coordenador (STUDIO_PRODUCTION_MODE)
    secrets_root: Path | None = None  # cofre de segredos (F10-07); None = <storage_root>/secrets
    google_client_secret_file: Path | None = None  # app OAuth web do Google (F8-05); lido no lugar, nunca copiado
    google_oauth_redirect_uri: str = "http://localhost:8000/studio/oauth/callback"
    # RP-032: disponibilidade do caminho baseado em plano. Não é um dispatch dual (o legado
    # foi removido): desligar recusa o render e a volta é o redeploy da imagem anterior.
    render_plan_enabled: bool = True
    # F01.T04 (contingência): desliga a publicação sem alterar código nem credencial.
    publication_enabled: bool = True
    # F06.T02: habilita o roteamento de provider em modo produção (exclui demo/placeholder).
    # Desligado no padrão preserva o painel/dev; só uma instalação real deve ligar (STUDIO_PROVIDER_PRODUCTION=1).
    provider_production: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        secrets_root = env.get("STUDIO_SECRETS_ROOT") or None
        return cls(env.get("STUDIO_DATABASE_URL") or None, Path(env.get("STUDIO_STORAGE_ROOT", "/data")),
                   _csv(env.get("STUDIO_SOURCE_ALLOWLIST"), DEFAULT_ALLOWLIST), _csv(env.get("STUDIO_ALLOW_NAMES"), DEFAULT_ALLOW_NAMES),
                   _cap(env.get("MAX_COST_USD_PER_VIDEO"), 0.0), _cap(env.get("MAX_COST_USD_PER_MONTH"), 15.0),
                   env.get("OPENCODE_BRIDGE_TOKEN", ""), env.get("OPENCODE_BRIDGE_URL") or "http://host.docker.internal:8787",
                   env.get("PEXELS_API_KEY", ""), _cap(env.get("STUDIO_PAID_IMAGE_USD"), 0.05), _cap(env.get("STUDIO_VEO_USD_PER_SECOND"), 0.40),
                   max(1, min(4, int(_cap(env.get("RENDER_CONCURRENCY"), 1)))),
                   _csv(env.get("STUDIO_TREND_SOURCES"), ("www.googleapis.com", "www.youtube.com")),
                   Path(env.get("STUDIO_TOKEN_ENV_PATH", "credentials/token.env")), _flag(env.get("STUDIO_BUDGET_GUARD")),
                   _production_mode(env.get("STUDIO_PRODUCTION_MODE")),
                   Path(secrets_root) if secrets_root else None,
                   Path(env["STUDIO_GOOGLE_CLIENT_SECRET_FILE"]) if env.get("STUDIO_GOOGLE_CLIENT_SECRET_FILE") else None,
                   env.get("STUDIO_GOOGLE_OAUTH_REDIRECT_URI") or "http://localhost:8000/studio/oauth/callback",
                   _flag(env.get("STUDIO_RENDER_PLAN_ENABLED", "1")),
                   _flag(env.get("STUDIO_PUBLICATION_ENABLED", "1")),
                   _flag(env.get("STUDIO_PROVIDER_PRODUCTION")))


RETRY_SECONDS = 5.0
PING_TTL_SECONDS = 5.0
CONNECT_OPTIONS = "-c lock_timeout=5000 -c statement_timeout=15000"  # nenhuma consulta espera para sempre
