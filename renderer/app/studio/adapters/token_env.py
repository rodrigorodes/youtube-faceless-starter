"""Refresh token do YouTube lido do `token.env` (F8-05), sem copiar o arquivo nem logar o valor.

Usado apenas como fallback quando o projeto ainda não tem consentimento no cofre. O arquivo é lido
a cada chamada (permite rotação manual) e o valor nunca sai da memória deste adaptador.
"""
from __future__ import annotations

from pathlib import Path

from ..application.ports import AccessToken, OAuthClient
from ..domain.youtube_oauth import OAuthReconnectRequired


class EnvRefreshTokenProvider:
    def __init__(self, oauth: OAuthClient, env_path: Path | str, variable: str = "YOUTUBE_REFRESH_TOKEN"):
        self.oauth, self.env_path, self.variable = oauth, Path(env_path), variable

    def __repr__(self) -> str:
        return f"EnvRefreshTokenProvider(path={str(self.env_path)!r}, var={self.variable!r}, token=***)"

    __str__ = __repr__

    def _token(self) -> str:
        try:
            lines = self.env_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            raise OAuthReconnectRequired("the YouTube token environment file is unavailable") from None
        for line in lines:
            name, sep, value = line.partition("=")
            if sep and name.strip() == self.variable:
                token = value.strip().strip('"').strip("'")
                if token:
                    return token
        raise OAuthReconnectRequired(f"{self.variable} is not set in the token environment file")

    def execute(self, project_id: str) -> AccessToken:
        """Devolve o access token de ambiente e **nenhum** canal: o refresh token do arquivo não
        passou por uma conferência de identidade (YT-03). Com destino configurado, o gate de
        publicação falha fechado em vez de presumir o canal.
        """
        return AccessToken(self.oauth.refresh(self._token()).access_token)