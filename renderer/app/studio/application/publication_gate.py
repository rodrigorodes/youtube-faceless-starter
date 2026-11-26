"""Gate único da publicação: a versão exata aprovada é a que vai ao YouTube (F01/W5.1/W5.2).

Dois caminhos publicam: `RunPublication` (o caminho **efetivo**, `POST /publications/execute`) e
`ClaimPublication` (o caminho legado que servia o workflow n8n, hoje inativo). Os dois precisam do
**mesmo** gate — fail-closed: sem intenção de publicação, com destino/metadados divergentes ou com
render/checksum/QA diferentes da aprovação, a publicação não prossegue. Um dono só evita que os
caminhos divirjam (achado 1 do `evidence/VERIFIED-FINDINGS.md`).
"""
from __future__ import annotations

from collections.abc import Callable

from ..domain.asset_registry import verify_license_provenance
from ..domain.contracts import Video
from ..domain.ids import InvalidId
from ..domain.publish import default_title
from ..domain.publication_policy import (PublicationGateError, PublicationIntentObsolete,
                                         verify_publication_gate, verify_publication_intent)

MISSING_INTENT = "the publication intent is missing; re-approve the video with a reviewed render"
NO_RENDER = "there is no successful render to publish"

LicenseNormalizer = Callable[[str | None], str | None]


def license_block_reason(
    video_id: str,
    *,
    scripts,
    assets,
    license_normalizer: LicenseNormalizer | None = None,
) -> str | None:
    """Verifica fail-closed todos os assets primários e secundários (`scene_assets`) do vídeo.

    Recusa publicação quando qualquer asset referenciado não existe no repositório (`None`) ou
    carrega licença fora da allowlist canônica.
    """
    if scripts is None or assets is None:
        return None
    for sc in scripts.scenes(video_id):
        refs: list[tuple[str, str]] = []
        seen_ids: set[str] = set()
        if sc.asset_id:
            refs.append(("primary", sc.asset_id))
            seen_ids.add(sc.asset_id)
        if hasattr(scripts, "get_scene_assets"):
            for sa in scripts.get_scene_assets(sc.id):
                sa_asset_id = getattr(sa, "asset_id", None)
                if sa_asset_id and sa_asset_id not in seen_ids:
                    role = getattr(sa, "role", "layer") or "layer"
                    refs.append((f"scene_asset:{role}", sa_asset_id))
                    seen_ids.add(sa_asset_id)
        for role, asset_id in refs:
            ast = assets.get(asset_id)
            if ast is None:
                return f"scene {sc.id} ({role}) references missing asset {asset_id}; publication is blocked"
            effective_license = license_normalizer(ast.license) if license_normalizer is not None else ast.license
            if not verify_license_provenance(effective_license):
                return f"scene {sc.id} ({role}) has asset {asset_id} with unverified license {ast.license!r}"
    return None


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


def publication_block_reason(
    video: Video,
    *,
    intents,
    approvals,
    jobs,
    channels=None,
    scripts=None,
    assets=None,
    license_normalizer: LicenseNormalizer | None = None,
) -> str | None:
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
    lic_block = license_block_reason(video.id, scripts=scripts, assets=assets,
                                     license_normalizer=license_normalizer)
    if lic_block is not None:
        return lic_block
    return None
