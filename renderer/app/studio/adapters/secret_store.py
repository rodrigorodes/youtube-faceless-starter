"""Cofre de segredos em arquivo (F10-07).

Cada escopo (`youtube:<project_id>`) é um JSON `{chave: valor}` com permissão 0600 dentro de um
diretório 0700, fora do banco e fora do `Project.config`. Escrita atômica (tmp + replace) para não
deixar arquivo meio escrito. Não há API de listagem de valores: só nomes.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path

_SCOPE_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_KEY_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class SecretStoreError(RuntimeError):
    """O cofre não pôde ler/gravar (caminho inválido ou conteúdo corrompido)."""


def _check(scope: object, key: object) -> None:
    if not isinstance(scope, str) or not _SCOPE_RE.match(scope) or ".." in scope:
        raise SecretStoreError("invalid secret scope")
    if not isinstance(key, str) or not _KEY_RE.match(key):
        raise SecretStoreError("invalid secret key")


class FileSecretStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = threading.Lock()

    def _path(self, scope: str) -> Path:
        return self.root / (re.sub(r"[^A-Za-z0-9._-]", "_", scope) + ".json")

    def _read(self, scope: str) -> dict[str, str]:
        path = self._path(scope)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise SecretStoreError("secret store is unavailable") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SecretStoreError("secret store file is corrupt") from exc
        if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
            raise SecretStoreError("secret store file is corrupt")
        return data

    def _write(self, scope: str, data: dict[str, str]) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.root, 0o700)
            path = self._path(scope)
            fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".tmp-", text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, ensure_ascii=False, sort_keys=True)
                os.chmod(tmp, 0o600)
                os.replace(tmp, path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except OSError as exc:
            raise SecretStoreError("secret store is unavailable") from exc

    def get(self, scope: str, key: str) -> str | None:
        _check(scope, key)
        with self._lock:
            return self._read(scope).get(key)

    def set(self, scope: str, key: str, value: str) -> None:
        _check(scope, key)
        if not isinstance(value, str) or not value:
            raise SecretStoreError("secret value must be a non-empty string")
        with self._lock:
            data = self._read(scope)
            data[key] = value
            self._write(scope, data)

    def delete(self, scope: str, key: str) -> None:
        _check(scope, key)
        with self._lock:
            data = self._read(scope)
            if key in data:
                del data[key]
                if data:
                    self._write(scope, data)
                else:
                    try:
                        self._path(scope).unlink()
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        raise SecretStoreError("secret store is unavailable") from exc

    def names(self, scope: str) -> tuple[str, ...]:
        _check(scope, "x")  # valida o escopo; a chave é só um placeholder
        with self._lock:
            return tuple(sorted(self._read(scope)))