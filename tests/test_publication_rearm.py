"""Publicação bloqueada antes de qualquer envio pode ser rearmada; o resto continua exigindo humano.

Bug: o gate bloqueou a publicação (canal sem destino) e o registro virou dead-letter para sempre. Depois
de corrigir a causa (conectar o canal) não havia caminho de volta: `retry` sempre recusa e o `claim` não
cria outra publicação. Resultado: o vídeo, já renderizado e aprovado, parecia precisar de render de novo.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.editorial import StateConflict  # noqa: E402
from app.studio.application.publishing import RearmPublication  # noqa: E402

V = "v" * 32


class Videos:
    def get_video(self, video_id):
        return object() if video_id == V else None


class Pubs:
    def __init__(self, result):
        self.result, self.calls = result, []

    def rearm_blocked(self, video_id):
        self.calls.append(video_id)
        return self.result


def test_rearm_returns_the_requeued_publication():
    pub = object()
    pubs = Pubs(pub)
    assert RearmPublication(Videos(), pubs).execute(V) is pub
    assert pubs.calls == [V]


def test_rearm_refuses_when_the_repository_cannot_prove_nothing_was_sent():
    with pytest.raises(StateConflict, match="reconciliation|reconciliação"):
        RearmPublication(Videos(), Pubs(None)).execute(V)


def test_rearm_requires_an_existing_video():
    from app.studio.application.editorial import VideoNotFound
    with pytest.raises(VideoNotFound):
        RearmPublication(Videos(), Pubs(object())).execute("x" * 32)
