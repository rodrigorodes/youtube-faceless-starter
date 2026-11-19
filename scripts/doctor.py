"""Diagnóstico do ambiente (macOS, Windows e Linux; só biblioteca padrão).

Uso: python scripts/doctor.py   (código de saída 1 se algum item obrigatório falhar)
Nunca imprime valores do .env: só nomes de variáveis e resultados.
"""
import os
import socket
import stat
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ["POSTGRES_PASSWORD", "N8N_ENCRYPTION_KEY"]


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def parse_env(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def check_env(env_text: str, required: list[str], optional: list[str] = ()) -> list[Check]:
    values = parse_env(env_text)
    checks = []
    for names, is_required in ((required, True), (optional, False)):
        for name in names:
            if name not in values:
                checks.append(Check(name, False, "ausente", is_required))
            elif not values[name]:
                checks.append(Check(name, False, "em branco", is_required))
            elif values[name].upper().startswith("CHANGE_ME"):
                checks.append(Check(name, False, "placeholder do .env.example não trocado", is_required))
            else:
                checks.append(Check(name, True, "definida", is_required))
    return checks


def check_port(host: str, port: int, expect_open: bool) -> Check:
    try:
        with socket.create_connection((host, port), timeout=2):
            is_open = True
    except OSError:
        is_open = False
    return Check(f"porta {port}", is_open == expect_open, "aberta" if is_open else "fechada")


def check_http(url: str, timeout: float = 3.0, required: bool = True) -> Check:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - URL local fixa
            return Check(url, 200 <= resp.status < 300, f"HTTP {resp.status}", required)
    except urllib.error.HTTPError as exc:
        return Check(url, False, f"HTTP {exc.code}", required)
    except (urllib.error.URLError, OSError) as exc:
        return Check(url, False, type(exc).__name__, required)


def check_env_permissions(path: Path) -> Check:
    if os.name == "nt":
        return Check(".env permissões", True, "não verificado no Windows", False)
    open_bits = stat.S_IMODE(path.stat().st_mode) & 0o077
    return Check(".env permissões", open_bits == 0, "600" if open_bits == 0 else "mais aberta que 600 (rode chmod 600 .env)", False)


def run_all(root: Path = ROOT, network: bool = True) -> list[Check]:
    env_path = root / ".env"
    if not env_path.exists():
        return [Check(".env", False, "arquivo ausente (copie .env.example para .env)")]
    text = env_path.read_text(encoding="utf-8")
    values = parse_env(text)
    needs_bridge = "opencode" in (values.get("AI_PROVIDER", "").lower(), values.get("IMAGE_PROVIDER", "").lower())
    checks = [Check(".env", True, "presente"), check_env_permissions(env_path)]
    checks += check_env(text, REQUIRED + (["OPENCODE_BRIDGE_TOKEN"] if needs_bridge else []),
                        [] if needs_bridge else ["OPENCODE_BRIDGE_TOKEN"])
    if network:
        checks.append(check_http("http://localhost:8000/health"))
        checks.append(check_http("http://localhost:5678/healthz"))
        checks.append(check_http("http://localhost:8787/health", required=needs_bridge))
    return checks


def main(root: Path = ROOT, network: bool = True) -> int:
    checks = run_all(root, network)
    for c in checks:
        mark = "OK  " if c.ok else ("FALHA" if c.required else "aviso")
        print(f"[{mark}] {c.name}: {c.detail}")
    failed = [c for c in checks if c.required and not c.ok]
    print(f"\n{len(failed)} falha(s) obrigatória(s)." if failed else "\nAmbiente OK.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
