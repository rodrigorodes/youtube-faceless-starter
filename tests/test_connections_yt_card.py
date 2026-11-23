"""Cartão "Canal do YouTube" das Conexões: conta já autorizada ≠ desconectado.

Bug real: o OAuth concluía e o Studio guardava a autorização, mas o cartão seguia dizendo
"Desconectado — Conectar conta Google" enquanto o canal do estúdio não estava vinculado. A única
ação visível era autorizar de novo (3 autorizações iguais no banco), e o passo que faltava
("Vincular") ficava dentro de "Avançado e diagnóstico".
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.panel_connections import render_connections  # noqa: E402
from app.studio.domain.channel import ChannelProfile  # noqa: E402

PROJECT = "a" * 32
YT = "UC9I2afuFatbDqQbyATyeZdQ"


def _channel(grant: str, status: str = "CONNECTED", expires: str = "2026-11-23T18:58:11+00:00") -> dict:
    return {"youtube_channel_id": YT, "title": "Rodrigo Mendes", "grant_id": grant, "status": status,
            "token_expires_at": expires, "studio_channels": []}


def _board(*channels: dict) -> dict:
    return {"accounts": [{"id": "acc1", "email": "eu@gmail.com", "display_name": "", "channels": list(channels)}]}


def _profile(youtube: str | None = None) -> ChannelProfile:
    return ChannelProfile(id=PROJECT, project_id=PROJECT, name="Musica", youtube_channel_id=youtube)


def _card(board: dict, profile: ChannelProfile) -> str:
    html, _ = render_connections(board, [profile], project_id=PROJECT)
    start = html.index("<h3>Canal do YouTube</h3>")
    return html[start - 40:html.index("conexoes-status", start)]


def test_authorized_account_not_yet_linked_asks_to_link_not_to_authorize_again():
    card = _card(_board(_channel("g1"), _channel("g2")), _profile())
    text = " ".join(re.sub(r"<[^>]+>", " ", card).split())
    assert "Desconectado" not in text
    assert "falta vincular" in text.lower() and "Rodrigo Mendes" in text
    assert "não precisa autorizar de novo" in text.lower()
    # a ação principal é vincular, com o canal e a versão reais do estúdio
    assert re.search(rf'data-link-direct[^>]*data-profile="{PROJECT}"[^>]*data-youtube="{YT}"', card)
    assert 'data-version="' in card
    assert "Conectar conta Google" not in text  # reautorizar vira ação secundária


def test_linked_and_connected_keeps_the_connected_state():
    board = _board(_channel("g1"))
    board["accounts"][0]["channels"][0]["studio_channels"] = [{"id": PROJECT, "name": "Musica"}]
    card = _card(board, _profile(YT))
    assert "✓ Conectado" in card and "data-link-direct" not in _markup(card)


def _markup(html: str) -> str:
    return re.sub(r"<script\b.*?</script>", "", html, flags=re.S)


def test_without_any_authorization_it_still_asks_to_connect():
    html, _ = render_connections({"accounts": []}, [_profile()], project_id=PROJECT)
    markup = _markup(html)
    assert "○ Desconectado" in markup and "Conectar conta Google" in markup
    assert "data-link-direct" not in markup


def test_expired_or_revoked_authorization_is_not_offered_for_linking():
    card = _card(_board(_channel("g1", status="REVOKED")), _profile())
    assert "data-link-direct" not in _markup(card) and "Conectar conta Google" in card


def test_duplicate_authorizations_of_the_same_channel_are_listed_once():
    html, _ = render_connections(_board(_channel("g1"), _channel("g2"), _channel("g3")), [_profile()], project_id=PROJECT)
    assert html.count('data-revoke data-grant="') == 1
    assert html.count(f'id="canal-{YT}"') == 1
