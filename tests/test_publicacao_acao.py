"""O botão da aba Publicação executa a publicação de verdade e mostra o resultado traduzido.

Antes, `#btn-publicar-acao` só validava o agendamento: o clique não chamava API nenhuma.
O JS roda em Node, sem rede, com `fetch` simulado.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_video_workspace import VIDEO, _content, _preview, _render, _view  # noqa: E402

from app.studio.api.panel_video_workspace import render_video_workspace  # noqa: E402
from app.studio.api.publicacao_js import PUBLICACAO_JS  # noqa: E402
from app.studio.domain.panel import Stage  # noqa: E402
from app.studio.domain.contracts import VideoStatus  # noqa: E402

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node indisponível")


def _explicar(resultado):
    script = ("global.window = {};" + PUBLICACAO_JS +
              f"process.stdout.write(JSON.stringify(window.StudioPublicacao.explicar({json.dumps(resultado)})));")
    return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)


def test_button_has_a_feedback_area_and_the_page_ships_the_publish_script():
    html, _ = render_video_workspace(
        _view(status=VideoStatus.AWAITING_APPROVAL, stage=Stage.AWAITING_APPROVAL), "publicacao", preview=_preview())
    content = _content(html)
    assert 'id="btn-publicar-acao"' in content
    assert re.search(r'id="publicar-feedback"[^>]*role="status"', content)
    assert "/publication/publish" in html  # o clique chama a API existente
    assert "StudioPublicacao" in html and "StudioAprovacao" in html


def test_button_is_disabled_with_a_reason_when_nothing_can_be_published_yet():
    html = _render("publicacao", view=_view(status=VideoStatus.IDEA, stage=Stage.PENDING))
    tag = re.search(r'<button[^>]*id="btn-publicar-acao"[^>]*>', _content(html)).group(0)
    assert "disabled" in tag
    assert "Aprove uma versão" in _content(html)


def test_button_is_enabled_when_the_version_is_awaiting_approval_or_approved():
    for status, stage in ((VideoStatus.AWAITING_APPROVAL, Stage.AWAITING_APPROVAL), (VideoStatus.APPROVED, Stage.APPROVED)):
        tag = re.search(r'<button[^>]*id="btn-publicar-acao"[^>]*>',
                        _content(_render("publicacao", view=_view(status=status, stage=stage)))).group(0)
        assert "disabled" not in tag, status


@needs_node
def test_uploaded_is_success_with_the_youtube_id():
    out = _explicar({"result": "UPLOADED", "youtube_video_id": "abc123XYZ"})
    assert out["ok"] is True and "Publicado no YouTube" in out["texto"] and "abc123XYZ" in out["texto"]


@needs_node
def test_blocked_by_missing_destination_is_explained_with_the_next_step_and_keeps_the_technical_reason():
    detail = "no YouTube destination is configured for this channel; connect the channel in Canais → Conexão"
    out = _explicar({"result": "BLOCKED", "detail": detail})
    assert out["ok"] is False
    assert "Conexões" in out["texto"] and "destino" in out["texto"]
    assert detail in out["texto"]


@needs_node
def test_other_outcomes_never_pretend_success():
    idle = _explicar({"result": "IDLE"})
    retry = _explicar({"result": "RETRY", "detail": "HTTP 503"})
    recon = _explicar({"result": "RECONCILE", "detail": "the uploader raised (TimeoutError); the remote state is unknown"})
    dead = _explicar({"result": "DEAD_LETTER", "detail": "something odd"})
    for out in (idle, retry, recon, dead):
        assert out["ok"] is False
    assert "Nada para publicar" in idle["texto"]
    assert "nova tentativa" in retry["texto"]
    assert "não reenvie" in recon["texto"].lower()
    assert "something odd" in dead["texto"]


@needs_node
def test_stale_approval_and_expired_schedule_are_explained():
    assert "Aprove a versão de novo" in _explicar(
        {"result": "BLOCKED", "detail": "the video metadata changed since the publication intent; confirm the publication again"})["texto"]
    assert "horário" in _explicar(
        {"result": "BLOCKED", "detail": "publication schedule has expired or is too close; reschedule before publishing"})["texto"]
