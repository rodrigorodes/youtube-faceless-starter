#!/usr/bin/env python3
"""CLI de consentimento OAuth do YouTube (F8-05), para habilitar a publicação real depois.

Grava o refresh token **no SecretStore** do Studio (nunca no client secret e nunca em log). O
arquivo de client secret é lido no caminho original, somente leitura; nenhum token é impresso.

Exemplos:
  PYTHONPATH=renderer python3 scripts/youtube_oauth_consent.py url --project-id <id>
  PYTHONPATH=renderer python3 scripts/youtube_oauth_consent.py exchange --project-id <id> \
      --code '<code>' --state '<state>'
  PYTHONPATH=renderer python3 scripts/youtube_oauth_consent.py status --project-id <id>
  PYTHONPATH=renderer python3 scripts/youtube_oauth_consent.py revoke --project-id <id>

Variáveis: STUDIO_DATABASE_URL, STUDIO_SECRETS_ROOT (ou STUDIO_STORAGE_ROOT),
STUDIO_GOOGLE_CLIENT_SECRET_FILE e STUDIO_GOOGLE_OAUTH_REDIRECT_URI.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _fail(message: str, code: int = 2) -> int:
    print(f"error: {message}", file=sys.stderr)
    return code


def _services(env, *, client=None, store=None, repo=None):
    from app.studio.adapters.google_oauth import google_oauth_from_client_secret
    from app.studio.adapters.postgres.youtube_channel_repo import PostgresYouTubeChannelRepository
    from app.studio.adapters.secret_store import FileSecretStore

    if client is None:
        secret_file = env.get("STUDIO_GOOGLE_CLIENT_SECRET_FILE")
        if not secret_file:
            raise ValueError("STUDIO_GOOGLE_CLIENT_SECRET_FILE is required")
        client = google_oauth_from_client_secret(Path(secret_file),
                                                 redirect_uri=env.get("STUDIO_GOOGLE_OAUTH_REDIRECT_URI") or
                                                 "http://localhost:8000/studio/oauth/callback")
    if store is None:
        root = env.get("STUDIO_SECRETS_ROOT") or str(Path(env.get("STUDIO_STORAGE_ROOT", "/data")) / "secrets")
        store = FileSecretStore(Path(root))
    if repo is None:
        dsn = env.get("STUDIO_DATABASE_URL")
        if not dsn:
            raise ValueError("STUDIO_DATABASE_URL is required")
        import psycopg
        repo = PostgresYouTubeChannelRepository(lambda: psycopg.connect(dsn))
    return client, store, repo


def main(argv: list[str] | None = None, env: dict[str, str] | None = None, *, client=None, store=None,
         repo=None, out=print) -> int:
    env = dict(os.environ if env is None else env)
    parser = argparse.ArgumentParser(description="YouTube OAuth consent for CERC Studio")
    parser.add_argument("command", choices=("url", "exchange", "status", "revoke"))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--code", default="")
    parser.add_argument("--state", default="")
    args = parser.parse_args(argv)

    try:
        client, store, repo = _services(env, client=client, store=store, repo=repo)
    except Exception as exc:  # configuração inválida: mensagem curta, sem segredo
        return _fail(f"cannot configure OAuth ({type(exc).__name__})")

    from app.studio.application.youtube_channels import GetYouTubeChannel
    from app.studio.application.youtube_oauth import (BeginConsent, CompleteConsent, RevokeConsent)

    redirect = env.get("STUDIO_GOOGLE_OAUTH_REDIRECT_URI") or "http://localhost:8000/studio/oauth/callback"
    try:
        if args.command == "url":
            result = BeginConsent(client, store, redirect_uri=redirect).execute(args.project_id)
            out(json.dumps({"authorization_url": result["authorization_url"], "state": result["state"],
                            "expires_at": result["expires_at"]}, ensure_ascii=False, indent=2))
        elif args.command == "exchange":
            if not args.code or not args.state:
                return _fail("exchange needs --code and --state")
            result = CompleteConsent(client, repo, store, redirect_uri=redirect).execute(
                args.project_id, args.code, args.state)
            out(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "status":
            out(json.dumps(GetYouTubeChannel(repo, store).execute(args.project_id), ensure_ascii=False, indent=2))
        else:
            out(json.dumps(RevokeConsent(client, repo, store).execute(args.project_id), ensure_ascii=False, indent=2))
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())