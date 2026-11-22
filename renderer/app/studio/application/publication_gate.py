"""Gate único da publicação: a versão exata aprovada é a que vai ao YouTube (F01/W5.1/W5.2).

Dois caminhos publicam: `RunPublication` (o caminho **efetivo**, `POST /publications/execute`) e
`ClaimPublication` (o caminho legado que servia o workflow n8n, hoje inativo). Os dois precisam do
**mesmo** gate — fail-closed: sem intenção de publicação, com destino/metadados divergentes ou com
render/checksum/QA diferentes da aprovação, a publicação não prossegue. Um dono só evita que os
caminhos divirjam (achado 1 do `evidence/VERIFIED-FINDINGS.md`).
"""
from __future__ import annotations

from ..domain.contracts import Video
from ..domain.ids import InvalidId
from ..domain.publish import default_title
from ..domain.publication_policy import (PublicationGateError, PublicationIntentObsolete,
                                         verify_publication_gate, verify_publication_intent)

MISSING_INTENT = "the publication intent is missing; re-approve the video with a reviewed render"
NO_RENDER = "there is no successful render to publish"


def confirmed_destination(video: Video, intent, channels) -> str | None:
    """Destino do YouTube que a intenção confirmou (A19); sem os repositórios de canal, o da intenção.

    Sem como observar o canal (construção legada/testes) devolver o próprio destino da intenção
    evita acusar uma mudança que não foi medida: `None` reprovaria qualquer intenção com destino.
    O caminho do servidor sempre injeta os repositórios (`composition.py`).
    """
    if channels is None:
        return intent.youtube_channel_id
    try:
        channel = channels.get_by_project(video.project_id)
    except InvalidId:
        channel = None
    return channel.youtube_channel_id if channel is not None else None


def publication_block_reason(video: Video, *, intents, approvals, jobs, channels=None) -> str | None:
    """Motivo pelo qual a publicação deste vídeo não pode prosseguir; `None` quando pode.

    Não escreve nada: quem chama decide o que fazer com o motivo (bloquear a publicação, marcar
    falha ou recusar o claim).
    """
    intent = intents.get(video.id)
    if intent is None:
        return MISSING_INTENT
    approval = approvals.get(video.id)
    job = jobs.latest(video.id)
    output = jobs.approved_output(video.id)
    if job is None or output is None:
        return NO_RENDER
    try:
        verify_publication_intent(intent, youtube_channel_id=confirmed_destination(video, intent, channels),
                                  title=video.title or default_title(video.topic),
                                  description=video.description or "", tags=video.tags)
        verify_publication_gate(intent, render_id=job.id, checksum=output.cache_key,
                                output_asset_id=output.id,
                                qa_report_passed=bool(video.qa_report and video.qa_report.is_publishable),
                                approval_output_asset_id=approval.output_asset_id if approval else None)
    except (PublicationGateError, PublicationIntentObsolete) as exc:
        return str(exc)
    return None
