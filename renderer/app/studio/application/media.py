"""Casos de uso de mídia: storyboard e produção de imagens por cena (cache por conteúdo, licença obrigatória)."""
from pathlib import Path
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from ..domain.asset_registry import requires_attribution, verify_license_provenance
from ..domain.contracts import Asset, AssetKind, Scene, SceneAsset as DomainSceneAsset, Video, VideoStatus
from ..domain.ids import asset_cache_key, check_id
from ..domain.media import ASPECT_FOR, build_image_prompt, strip_style
from ..domain.media_ranker import MediaRanker
from .budget import PaidOperationGuard, paid_key, provider_settlement
from .editorial import CostGuard, StateConflict, VideoNotFound, _require_video
from .errors import ProjectNotFound, ServiceUnavailable
from .ports import (AssetRepository, AssetStore, ChannelProfileRepository, ImageModel, MediaCandidate, MediaFetcher, MediaProbe, MediaSearch,
                    ProductionLock, ScriptRepository, UsageRepository, VideoRepository)

ALLOWED_IMAGE_MIME = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_VIDEO_MIME = {"video/mp4", "video/webm"}
ALLOWED_MIME = ALLOWED_IMAGE_MIME | ALLOWED_VIDEO_MIME


class AssetRefused(ValueError):
    """Imagem do provedor recusada (sem licença, tipo não raster ou arquivo inválido); nada é gravado nem vinculado."""


class SceneNotFound(LookupError):
    """A cena referenciada não existe neste vídeo (id estável)."""


class SceneMediaRefused(ValueError):
    """Troca de mídia recusada por escolha inválida (nada gravado): candidato e asset juntos, asset inexistente ou sem fetcher."""


class PrepareStoryboard:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository):
        self.videos, self.scripts = videos, scripts

    def execute(self, video_id: str) -> None:
        video = _require_video(self.videos, video_id)
        if video.status != VideoStatus.FACT_CHECKED:
            raise StateConflict(f"storyboard needs state FACT_CHECKED, got {video.status.value}")
        if not self.scripts.scenes(video_id):
            raise StateConflict("no scenes to storyboard: write a script first")
        if not self.videos.transition_video(video_id, VideoStatus.FACT_CHECKED, VideoStatus.STORYBOARDED):
            raise StateConflict("video state changed during the storyboard")


@dataclass(frozen=True)
class ProduceResult:
    generated: int
    reused: int


class ProduceAssets:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository, store: AssetStore,
                 guard: CostGuard, usage: UsageRepository, image_for: Callable[[str], ImageModel], lock: ProductionLock,
                 paid: PaidOperationGuard | None = None):
        self.videos, self.scripts, self.assets, self.store = videos, scripts, assets, store
        self.guard, self.usage, self.image_for, self.lock = guard, usage, image_for, lock
        self.paid = paid

    def execute(self, video_id: str) -> ProduceResult:
        """Retomável: cena já vinculada é pulada; imagem já no cache é reaproveitada; só o que falta é gerado.
        Uma execução por vídeo: a segunda recebe conflito em vez de gerar (e pagar) de novo em paralelo."""
        with self.lock.hold(video_id) as acquired:
            if not acquired:
                raise StateConflict("asset production already in progress for this video")
            return self._run(video_id)

    def _run(self, video_id: str) -> ProduceResult:
        video = _require_video(self.videos, video_id)
        if video.status != VideoStatus.STORYBOARDED:
            raise StateConflict(f"asset production needs state STORYBOARDED, got {video.status.value}")
        model = self.image_for(video.project_id)
        aspect = ASPECT_FOR[video.format]
        generated = reused = 0
        for scene in self.scripts.scenes(video_id):
            if scene.asset_id:
                continue
            prompt = build_image_prompt(scene.image_prompt, aspect)
            key = asset_cache_key("image", model.name, model.model, prompt, {"aspect": aspect})
            asset = self.assets.find(key)
            if asset is None:
                asset = self._generate(video_id, model, prompt, aspect, key)
                generated += 1
            else:
                reused += 1
            if not self.assets.link_scene(video_id, scene.idx, asset.id, scene.image_prompt):
                raise StateConflict("video or scenes changed during asset production")
        if not self.videos.transition_video(video_id, VideoStatus.STORYBOARDED, VideoStatus.ASSETS_READY):
            raise StateConflict("video state changed during asset production")
        return ProduceResult(generated, reused)

    def _generate(self, video_id: str, model: ImageModel, prompt: str, aspect: str, key: str) -> Asset:
        estimate = model.cost_estimate(prompt)
        if self.paid is None:
            self.guard.check(video_id, estimate)  # antes da chamada
            result = model.generate(prompt, aspect=aspect)
            self.usage.record(video_id, result.usage)  # a chamada aconteceu: contabiliza mesmo se a imagem for recusada
        else:
            op_key = paid_key("image", video_id, key)

            def _validated(res):
                # imagem paga e inutilizável não pode encerrar o custo: valida antes de confirmar
                if not res.license.strip():
                    raise AssetRefused("image without a registered license")
                if res.mime not in ALLOWED_MIME:
                    raise AssetRefused(f"unsupported image mime {res.mime!r}")
                return res

            result = self.paid.run(op_key, video_id, Decimal(str(estimate)),
                                   call=lambda: model.generate(prompt, aspect=aspect),
                                   validate=_validated,
                                   settle=lambda res: provider_settlement(res.usage, settled_by=f"studio:image:{model.name}"))
        if not result.license.strip():
            raise AssetRefused("image without a registered license")
        if result.mime not in ALLOWED_MIME:
            raise AssetRefused(f"unsupported image mime {result.mime!r}")
        path = self.store.put(key, result.data, aspect)
        asset = Asset(id=uuid.uuid4().hex, kind=AssetKind.image, cache_key=key, path=path, provider=model.name, model=model.model,
                      license=result.license, attribution=result.attribution, source_url=result.source_url,
                      cost_usd=result.usage.cost_usd)
        return self.assets.add(asset)  # em corrida, devolve o asset que já existe para a chave


@dataclass(frozen=True)
class SceneAsset:
    idx: int
    asset: Asset | None


class ListAssets:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository):
        self.videos, self.scripts, self.assets = videos, scripts, assets

    def execute(self, video_id: str) -> list[SceneAsset]:
        _require_video(self.videos, video_id)
        return [SceneAsset(s.idx, self.assets.get(s.asset_id) if s.asset_id else None) for s in self.scripts.scenes(video_id)]


def _scene_by_id(scenes: list[Scene], scene_id: str) -> Scene | None:
    return next((scene for scene in scenes if scene.id == scene_id), None)


@dataclass(frozen=True)
class SceneCandidates:
    """Candidatos de mídia de uma cena; ``query`` é o tema usado (prompt sem o sufixo de estilo)."""

    scene_id: str
    query: str
    candidates: tuple[MediaCandidate, ...]


class ListSceneCandidates:
    """Lista candidatos de mídia para uma cena via ``MediaSearch`` (W4.4/VE-06).

    A busca é agnóstica de fornecedor e sai do tema do prompt da cena; busca vazia devolve lista
    vazia — o chamador mantém a mídia atual (fallback), sem cena sem imagem.
    """

    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, search: MediaSearch,
                 assets: AssetRepository | None = None):
        self.videos, self.scripts, self.search = videos, scripts, search
        self.assets = assets

    def execute(self, video_id: str, scene_id: str, *, per_page: int = 10,
                media_type: str = "image") -> SceneCandidates:
        video = _require_video(self.videos, video_id)
        all_scenes = self.scripts.scenes(video_id)
        scene = _scene_by_id(all_scenes, scene_id)
        if scene is None:
            raise SceneNotFound(scene_id)
        if self.search is None:
            raise ServiceUnavailable("media search is not configured")

        query = strip_style(scene.image_prompt).strip() or scene.caption.strip()
        orientation = "portrait" if ASPECT_FOR[video.format] == "9:16" else "landscape"

        all_candidates: list[MediaCandidate] = []
        seen_keys: set[str] = set()

        if query:
            found = self.search.search(query, media_type=media_type, orientation=orientation, per_page=per_page)
            for c in found:
                key = c.media_id or c.url
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_candidates.append(c)

        scene_queries = getattr(scene, "search_queries", None) or []
        for extra_q in scene_queries[:2]:
            clean_q = (extra_q or "").strip()
            if clean_q and clean_q.lower() != query.lower():
                extra_found = self.search.search(clean_q, media_type=media_type, orientation=orientation, per_page=per_page)
                for c in extra_found:
                    key = c.media_id or c.url
                    if key not in seen_keys:
                        seen_keys.add(key)
                        all_candidates.append(c)

        if not all_candidates:
            return SceneCandidates(scene_id=scene.id, query=query, candidates=())

        target_format = video.format.value if hasattr(video.format, "value") else str(video.format)
        visual_intent = getattr(scene, "visual_intent", "")
        queries = [query] if query else []
        for sq in scene_queries:
            if sq and sq not in queries:
                queries.append(sq)

        used_media_ids = set()
        for s in all_scenes:
            if s.id != scene.id and s.asset_id:
                used_media_ids.add(s.asset_id)
                if self.assets is not None:
                    asset = self.assets.get(s.asset_id)
                    if asset is not None and asset.model:
                        used_media_ids.add(asset.model)

        ranked = MediaRanker.rank(
            all_candidates,
            visual_intent=visual_intent,
            queries=queries,
            target_format=target_format,
            used_media_ids=used_media_ids,
        )
        ranked_candidates = tuple(sc.candidate for sc in ranked)[:per_page]
        return SceneCandidates(scene_id=scene.id, query=query, candidates=ranked_candidates)


@dataclass(frozen=True)
class SceneMediaResult:
    """Resultado da troca: asset final da cena e se houve escrita (``changed``); ``reason`` explica o no-op."""

    scene_id: str
    asset: Asset | None
    changed: bool
    reason: str = ""
    edit_revision: int | None = None
    trim_start_s: float | None = None
    trim_end_s: float | None = None


class SwapSceneMedia:
    """Troca a mídia de **uma** cena (id estável) sem tocar nas outras (W4.4/EDIT-03/VE-06).

    Aceita um ``asset_id`` já existente **ou** um ``candidate`` materializado pelo ``MediaFetcher``.
    Sem escolha (ambos nulos) mantém a mídia atual: nenhuma escrita, o fallback "sem candidato".
    Licença obrigatória nos dois caminhos; a troca é idempotente e compara-e-troca no vínculo lido
    (CAS) para não sobrescrever mudança concorrente. Só a cena alvo é escrita — o cache/render
    invalida apenas ela e o final por dependência (``PlanRegeneration``).
    """

    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository, store: AssetStore,
                 fetcher: MediaFetcher | None = None, guard: CostGuard | None = None,
                 usage: UsageRepository | None = None):
        self.videos, self.scripts, self.assets, self.store = videos, scripts, assets, store
        self.fetcher, self.guard, self.usage = fetcher, guard, usage

    def execute(self, video_id: str, scene_id: str, *, asset_id: str | None = None,
                candidate: MediaCandidate | None = None, expected_asset_id: str | None = None,
                expected_version: int | None = None, expected_edit_revision: int | None = None,
                apply_trim: bool = False, trim_start_s: float | None = None,
                trim_end_s: float | None = None) -> SceneMediaResult:
        import math

        video = _require_video(self.videos, video_id)
        scene = _scene(self.scripts, video_id, scene_id)
        if expected_version is not None:
            latest = self.scripts.latest(video_id)
            if latest is None or latest.version != expected_version:
                raise StateConflict("script version changed underneath the media swap")
        if expected_edit_revision is not None and getattr(scene, "edit_revision", 1) != expected_edit_revision:
            raise StateConflict("scene edit_revision changed underneath; reload before swapping")
        if apply_trim and (trim_start_s is not None or trim_end_s is not None):
            if trim_start_s is None or trim_end_s is None:
                raise SceneMediaRefused("both trim_start_s and trim_end_s are required when trim is specified")
            if not math.isfinite(trim_start_s) or not math.isfinite(trim_end_s) or trim_start_s < 0 or trim_end_s <= trim_start_s:
                raise SceneMediaRefused("invalid trim bounds: require finite 0 <= trim_start_s < trim_end_s")
        if asset_id is None and candidate is None:
            current = self.assets.get(scene.asset_id) if scene.asset_id else None
            return SceneMediaResult(scene_id=scene.id, asset=current, changed=False, reason="no_candidate",
                                    edit_revision=getattr(scene, "edit_revision", 1))
        if asset_id is not None and candidate is not None:
            raise SceneMediaRefused("choose either a candidate or an asset, not both")
        if candidate is not None:
            asset = self._materialize(video, candidate)
        else:
            asset = self.assets.get(asset_id)
            if asset is None:
                raise SceneMediaRefused(f"asset {asset_id!r} does not exist")
            if not (asset.license or "").strip():
                raise AssetRefused("asset without a registered license")
            if hasattr(self.assets, "belongs_to_other_project") and self.assets.belongs_to_other_project(asset.id, video.project_id):
                raise PermissionError(f"asset {asset.id!r} belongs to another project")
        if scene.asset_id == asset.id and not apply_trim:
            return SceneMediaResult(scene_id=scene.id, asset=asset, changed=False, reason="already-linked",
                                    edit_revision=getattr(scene, "edit_revision", 1))
        if expected_asset_id is not None and (scene.asset_id or "") != expected_asset_id:
            raise StateConflict("scene media changed underneath; reload before swapping")
        if hasattr(self.assets, "add_and_replace_scene_base_media"):
            persisted, new_rev, ok, reason = self.assets.add_and_replace_scene_base_media(
                video_id=video_id,
                scene_id=scene.id,
                existing_asset_id=asset.id,
                expected_asset_id=scene.asset_id,
                expected_edit_revision=expected_edit_revision,
                apply_trim=apply_trim,
                trim_start_s=trim_start_s,
                trim_end_s=trim_end_s,
            )
            if not ok or persisted is None:
                raise StateConflict(f"scene media changed underneath ({reason}); nothing was written")
            return SceneMediaResult(
                scene_id=scene.id,
                asset=persisted,
                changed=True,
                edit_revision=new_rev,
                trim_start_s=trim_start_s if apply_trim else None,
                trim_end_s=trim_end_s if apply_trim else None,
            )
        if not self.assets.swap_scene_asset(video_id, scene.id, asset.id, expected_asset_id=scene.asset_id):
            raise StateConflict("scene media changed underneath; nothing was written")
        return SceneMediaResult(scene_id=scene.id, asset=asset, changed=True,
                                edit_revision=getattr(scene, "edit_revision", 1) + 1)

    def _materialize(self, video: Video, candidate: MediaCandidate) -> Asset:
        if self.fetcher is None:
            raise SceneMediaRefused("no media fetcher is configured to apply a candidate")
        provider = self.fetcher.name
        aspect = ASPECT_FOR[video.format]
        estimate = Decimal(str(candidate.cost_usd)) if candidate.cost_usd is not None else Decimal("0")
        if self.guard is not None and estimate > 0:
            self.guard.check(video.id, float(estimate))  # antes de baixar: candidato pago respeita o teto
        result = self.fetcher.fetch(candidate)
        if not (result.license or "").strip():
            raise AssetRefused("candidate without a registered license")
        if result.mime not in ALLOWED_MIME:
            raise AssetRefused(f"unsupported image mime {result.mime!r}")
        key = asset_cache_key("image", provider, candidate.media_id or candidate.url, candidate.url, {"aspect": aspect, "license": candidate.license or result.license})
        existing = self.assets.find(key)
        if existing is not None:
            return existing  # mesmo candidato com o mesmo aspecto: reaproveita o asset já vinculável
        path = self.store.put(key, result.data, aspect)
        asset = Asset(id=uuid.uuid4().hex, kind=AssetKind.image, cache_key=key, path=path, provider=provider,
                      model=candidate.media_id or provider, license=result.license, attribution=result.attribution,
                      source_url=result.source_url, cost_usd=result.usage.cost_usd)
        if self.usage is not None:
            self.usage.record(video.id, result.usage)
        return self.assets.add(asset)


BROLL_NOTE_MAX = 200


@dataclass(frozen=True)
class SceneBrollResult:
    scene_id: str
    enabled: bool
    note: str | None
    changed: bool


class SetSceneBroll:
    """Liga/desliga o B-roll de **uma** cena e grava a nota (UI do storyboard).

    Leve por desenho: não cria versão de roteiro nem limpa a mídia da cena. Idempotente — o mesmo
    valor não escreve (``changed=False``). A nota é normalizada (strip; vazia vira ``None``).
    """

    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository):
        self.videos, self.scripts, self.assets = videos, scripts, assets

    def execute(self, video_id: str, scene_id: str, *, enabled: bool, note: str | None = None) -> SceneBrollResult:
        _require_video(self.videos, video_id)
        scene = _scene(self.scripts, video_id, scene_id)
        clean = (note or "").strip() or None
        if clean is not None and len(clean) > BROLL_NOTE_MAX:
            raise SceneMediaRefused(f"broll note exceeds {BROLL_NOTE_MAX} characters")
        enabled = bool(enabled)
        if scene.broll_enabled == enabled and scene.broll_note == clean:
            return SceneBrollResult(scene_id=scene.id, enabled=enabled, note=clean, changed=False)
        if not self.assets.set_scene_broll(video_id, scene.id, enabled, clean):
            raise SceneNotFound(scene_id)
        return SceneBrollResult(scene_id=scene.id, enabled=enabled, note=clean, changed=True)


def _scene(scripts: ScriptRepository, video_id: str, scene_id: str) -> Scene:
    scene = _scene_by_id(scripts.scenes(video_id), scene_id)
    if scene is None:
        raise SceneNotFound(scene_id)
    return scene


class SceneAssetFile:
    """Arquivo da mídia vinculada a **uma** cena (preview do storyboard).

    Só devolve um arquivo regular dentro da raiz de armazenamento; qualquer outra coisa (cena sem
    mídia, caminho fora da raiz, arquivo ausente) é ``None`` e o chamador responde 404.
    """

    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository, root):
        self.videos, self.scripts, self.assets, self.root = videos, scripts, assets, root

    def execute(self, video_id: str, scene_id: str):
        from pathlib import Path
        _require_video(self.videos, video_id)
        scene = _scene(self.scripts, video_id, scene_id)
        asset = self.assets.get(scene.asset_id) if scene.asset_id else None
        if asset is None:
            return None
        root = Path(self.root).resolve()
        try:
            target = (root / asset.path).resolve()
            target.relative_to(root)
        except (ValueError, OSError):
            return None
        return target if target.is_file() else None


class AssetFile:
    """Arquivo de um asset registrado sob escopo de projeto ou vídeo.

    Garante fronteira de Clean Architecture sem acesso a repositórios diretamente na camada de rotas.
    Rejeita acesso cruzado (outro vídeo/projeto) e sem escopo (403), além de path traversal fora da raiz (404).
    """

    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository, root):
        self.videos, self.scripts, self.assets, self.root = videos, scripts, assets, root

    def execute(self, asset_id: str, *, video_id: str | None = None, project_id: str | None = None):
        from pathlib import Path
        if not video_id and not project_id:
            raise PermissionError("asset file request requires video_id or project_id scope")

        if video_id:
            video = _require_video(self.videos, video_id)
            if project_id and video.project_id != project_id:
                raise PermissionError("video does not belong to specified project")
        elif project_id:
            if hasattr(self.videos, "get_project"):
                proj = self.videos.get_project(project_id)
                if proj is None:
                    raise VideoNotFound(f"project {project_id!r} not found")

        authorized = False
        if hasattr(self.assets, "belongs_to_scope"):
            authorized = self.assets.belongs_to_scope(asset_id, video_id=video_id, project_id=project_id)
        else:
            if video_id:
                for sc in self.scripts.scenes(video_id):
                    if sc.asset_id == asset_id:
                        authorized = True
                        break
                    if hasattr(self.scripts, "get_scene_assets"):
                        sas = self.scripts.get_scene_assets(sc.id)
                        if any(sa.asset_id == asset_id for sa in sas):
                            authorized = True
                            break
            elif project_id:
                if hasattr(self.videos, "list_by_project"):
                    for v in self.videos.list_by_project(project_id):
                        for sc in self.scripts.scenes(v.id):
                            if sc.asset_id == asset_id:
                                authorized = True
                                break
                            if hasattr(self.scripts, "get_scene_assets"):
                                sas = self.scripts.get_scene_assets(sc.id)
                                if any(sa.asset_id == asset_id for sa in sas):
                                    authorized = True
                                    break
                        if authorized:
                            break

        if not authorized:
            raise PermissionError("asset does not belong to authorized scope")

        asset = self.assets.get(asset_id)
        if asset is None:
            return None

        root = Path(self.root).resolve()
        try:
            target = (root / asset.path).resolve()
            target.relative_to(root)
        except (ValueError, OSError):
            return None
        return target if target.is_file() else None


MAX_IMPORT_BYTES = 100 * 1024 * 1024


class ImportExternalMedia:
    """Importação genérica e assistida de mídia externa PNG/JPEG/WEBP e MP4/WebM (GAI-01).

    Valida MIME real via probe/decode sandboxed, tamanho máximo, licença/proveniência verificável,
    deduplica por conteúdo+escopo (sem filename na chave) e vincula com CAS + compensação atômica.
    """

    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository, store: AssetStore,
                 probe: MediaProbe | None = None):
        self.videos, self.scripts, self.assets, self.store = videos, scripts, assets, store
        self.probe = probe

    def execute(
        self,
        video_id: str,
        data: bytes,
        filename: str,
        mime: str,
        license: str,
        scene_id: str | None = None,
        attribution: str = "",
        source_url: str = "",
        expected_asset_id: str | None = None,
        trim_start_s: float | None = None,
        trim_end_s: float | None = None,
        expected_edit_revision: int | None = None,
    ) -> Asset:
        import hashlib
        import math
        from pathlib import PurePosixPath

        video = _require_video(self.videos, video_id)
        if (trim_start_s is not None) != (trim_end_s is not None):
            raise AssetRefused("both trim_start_s and trim_end_s are required when trim is specified")
        if trim_start_s is not None and trim_end_s is not None:
            if not math.isfinite(trim_start_s) or not math.isfinite(trim_end_s):
                raise AssetRefused("trim_start_s and trim_end_s must be finite numbers")
            if trim_start_s < 0.0 or trim_end_s <= trim_start_s:
                raise AssetRefused("invalid trim bounds: require 0 <= trim_start_s < trim_end_s")

        clean_license = (license or "").strip()
        if not verify_license_provenance(clean_license):
            raise AssetRefused("media without a valid registered open/commercial license")
        if requires_attribution(clean_license) and not ((attribution or "").strip() or (source_url or "").strip()):
            raise AssetRefused("selected license requires attribution or source_url")
        clean_source_url = (source_url or "").strip()
        if clean_source_url and not clean_source_url.lower().startswith(("http://", "https://")):
            raise AssetRefused("invalid source_url scheme")

        if not isinstance(filename, str) or "\x00" in filename or "%00" in filename:
            raise AssetRefused("invalid media filename")
        clean_filename = PurePosixPath(filename.replace("\\", "/")).name
        if not clean_filename or clean_filename in (".", "..") or clean_filename.startswith("."):
            raise AssetRefused("invalid media filename")

        mime_normalized = (mime or "").strip().lower()
        if mime_normalized not in ALLOWED_MIME:
            raise AssetRefused(f"unsupported media mime {mime!r}")

        if scene_id is not None:
            scene = _scene(self.scripts, video.id, scene_id)
            if expected_edit_revision is not None and getattr(scene, "edit_revision", 1) != expected_edit_revision:
                raise StateConflict("scene edit_revision changed underneath; reload before importing")
            if scene.asset_id != expected_asset_id:
                raise StateConflict("scene media changed underneath; reload before importing")

        if not data:
            raise AssetRefused("empty media payload")
        if len(data) > MAX_IMPORT_BYTES:
            raise AssetRefused("media exceeds 100MB limit")
        if self.probe is None:
            raise AssetRefused("media probe adapter is not configured")
        probed = self.probe.probe(data, mime_normalized)
        if trim_end_s is not None and probed is not None and getattr(probed, "duration_s", None) is not None:
            if float(trim_end_s) > float(probed.duration_s) + 1e-6:
                raise AssetRefused(
                    f"trim_end_s ({trim_end_s}) exceeds probed media duration ({float(probed.duration_s):.3f}s)"
                )

        is_video = mime_normalized in ALLOWED_VIDEO_MIME
        kind = AssetKind.video if is_video else AssetKind.image
        aspect = ASPECT_FOR.get(video.format.value if hasattr(video.format, "value") else str(video.format), "9:16")

        content_hash = hashlib.sha256(data).hexdigest()
        scope_params: dict[str, object] = {
            "license": clean_license.casefold(),
            "size": len(data),
        }
        if not is_video:
            scope_params["aspect"] = aspect
        key = asset_cache_key(kind.value, "import", video.project_id, content_hash, scope_params)

        existing = self.assets.find(key)
        if existing is not None:
            root = Path(self.store.root).resolve() if hasattr(self.store, "root") else None
            file_ok = False
            if root:
                try:
                    target = (root / existing.path).resolve()
                    target.relative_to(root)
                    file_ok = target.is_file()
                except (ValueError, OSError):
                    file_ok = False
            else:
                file_ok = True
            if file_ok:
                if scene_id is not None:
                    if hasattr(self.assets, "add_and_replace_scene_base_media"):
                        persisted, _rev, ok, reason = self.assets.add_and_replace_scene_base_media(
                            video_id=video.id,
                            scene_id=scene_id,
                            existing_asset_id=existing.id,
                            expected_asset_id=expected_asset_id,
                            expected_edit_revision=expected_edit_revision,
                            apply_trim=True,
                            trim_start_s=trim_start_s,
                            trim_end_s=trim_end_s,
                        )
                        if not ok or persisted is None:
                            raise StateConflict(f"scene media changed underneath ({reason}); nothing was linked")
                        return persisted
                    self._link_scene_cas(video.id, scene_id, existing.id, expected_asset_id)
                    self._apply_scene_trim(scene_id, existing.id, trim_start_s, trim_end_s)
                return existing

        if is_video and hasattr(self.store, "put_video"):
            try:
                path = self.store.put_video(key, data, mime_normalized)
            except TypeError:
                path = self.store.put_video(key, data)
        else:
            path = self.store.put(key, data, aspect)

        if existing is not None:
            if scene_id is not None:
                if hasattr(self.assets, "add_and_replace_scene_base_media"):
                    persisted, _rev, ok, reason = self.assets.add_and_replace_scene_base_media(
                        video_id=video.id,
                        scene_id=scene_id,
                        existing_asset_id=existing.id,
                        expected_asset_id=expected_asset_id,
                        expected_edit_revision=expected_edit_revision,
                        apply_trim=True,
                        trim_start_s=trim_start_s,
                        trim_end_s=trim_end_s,
                    )
                    if not ok or persisted is None:
                        raise StateConflict(f"scene media changed underneath ({reason}); nothing was linked")
                    return persisted
                self._link_scene_cas(video.id, scene_id, existing.id, expected_asset_id)
                self._apply_scene_trim(scene_id, existing.id, trim_start_s, trim_end_s)
            return existing

        asset = Asset(
            id=uuid.uuid4().hex,
            kind=kind,
            cache_key=key,
            path=path,
            provider="import",
            model="manual_upload",
            license=clean_license,
            attribution=(attribution or "").strip(),
            source_url=clean_source_url,
            cost_usd=0.0,
        )
        saved: Asset | None = None
        use_unified_base_replace = (
            hasattr(self.assets, "add_and_replace_scene_base_media")
            and not (
                "add_and_swap_scene_asset" in type(self.assets).__dict__
                and "add_and_replace_scene_base_media" not in type(self.assets).__dict__
            )
        )
        try:
            if scene_id is not None and use_unified_base_replace:
                saved, _rev, linked, reason = self.assets.add_and_replace_scene_base_media(
                    video_id=video.id,
                    scene_id=scene_id,
                    asset=asset,
                    expected_asset_id=expected_asset_id,
                    expected_edit_revision=expected_edit_revision,
                    apply_trim=True,
                    trim_start_s=trim_start_s,
                    trim_end_s=trim_end_s,
                )
                if not linked or saved is None:
                    raise StateConflict(f"scene media changed underneath ({reason}); nothing was linked")
                return saved
            if scene_id is not None and hasattr(self.assets, "add_and_swap_scene_asset"):
                saved, linked = self.assets.add_and_swap_scene_asset(
                    asset, video.id, scene_id, expected_asset_id
                )
                if not linked:
                    raise StateConflict("scene media changed underneath; nothing was linked")
                self._apply_scene_trim(scene_id, saved.id, trim_start_s, trim_end_s)
                return saved
            saved = self.assets.add(asset)
            if scene_id is not None:
                self._link_scene_cas(video.id, scene_id, saved.id, expected_asset_id)
                self._apply_scene_trim(scene_id, saved.id, trim_start_s, trim_end_s)
            return saved
        except Exception:
            self._compensate_failed_import(cache_key=key, asset_id=asset.id, saved=saved, path=path)
            raise

    def _link_scene_cas(self, video_id: str, scene_id: str, asset_id: str, expected_asset_id: str | None) -> None:
        if hasattr(self.assets, "swap_scene_asset"):
            if not self.assets.swap_scene_asset(video_id, scene_id, asset_id, expected_asset_id):
                raise StateConflict("scene media changed underneath; nothing was linked")
        elif hasattr(self.assets, "set_scene_asset"):
            self.assets.set_scene_asset(video_id, scene_id, asset_id)

    def _apply_scene_trim(self, scene_id: str, asset_id: str, trim_start_s: float | None, trim_end_s: float | None) -> None:
        if trim_start_s is not None and trim_end_s is not None:
            sa = DomainSceneAsset(
                scene_id=scene_id,
                asset_id=asset_id,
                position=0,
                start_s=float(trim_start_s),
                end_s=float(trim_end_s),
                role="base",
                motion="none",
            )
            if hasattr(self.scripts, "save_scene_assets"):
                self.scripts.save_scene_assets(scene_id, [sa])
            elif hasattr(self.scripts, "add_scene_asset"):
                self.scripts.add_scene_asset(scene_id, sa)
        else:
            if hasattr(self.scripts, "save_scene_assets"):
                self.scripts.save_scene_assets(scene_id, [])

    def _compensate_failed_import(self, *, cache_key: str, asset_id: str, saved: Asset | None, path: str) -> None:
        if saved is not None and saved.id == asset_id and hasattr(self.assets, "delete_if_unreferenced"):
            try:
                self.assets.delete_if_unreferenced(saved.id)
            except Exception:
                return  # fail closed on DB ambiguity: never unlink a possibly live file
        try:
            still_exists = self.assets.find(cache_key)
            path_referenced = (
                self.assets.is_path_referenced(path)
                if hasattr(self.assets, "is_path_referenced")
                else False
            )
        except Exception:
            return  # fail closed on DB error: never unlink a possibly live file
        if still_exists is None and not path_referenced and hasattr(self.store, "delete"):
            try:
                self.store.delete(path)
            except Exception:
                pass


class GetSceneTiming:
    """Extrai os recortes de tempo (start_s, end_s) de cada cena pelo asset atualmente vinculado."""

    def __init__(self, scripts: ScriptRepository):
        self.scripts = scripts

    def execute(self, scenes: list[Scene]) -> dict[str, tuple[float, float]]:
        timing: dict[str, tuple[float, float]] = {}
        if not hasattr(self.scripts, "get_scene_assets") or not scenes:
            return timing
        for sc in scenes:
            if not getattr(sc, "asset_id", None):
                continue
            try:
                sas = self.scripts.get_scene_assets(sc.id)
            except Exception:
                continue
            matching = [sa for sa in sas if sa.role == "base" and sa.asset_id == sc.asset_id]
            if matching:
                timing[sc.id] = (float(matching[0].start_s), float(matching[0].end_s))
        return timing


class ManageAssetTags:
    """Gerenciamento de tags em assets com validação e escopo estrito de projeto."""

    def __init__(
        self,
        videos: VideoRepository,
        assets: AssetRepository,
        channels: ChannelProfileRepository | None = None,
    ):
        self.videos, self.assets, self.channels = videos, assets, channels

    def resolve_project_id(self, project_or_channel_id: str) -> str:
        pid = check_id(project_or_channel_id)
        if hasattr(self.videos, "get_project"):
            proj = self.videos.get_project(pid)
            if proj is not None:
                return pid
        if self.channels is not None:
            profile = self.channels.get(pid)
            if profile is not None:
                return profile.project_id
        if hasattr(self.videos, "get_project"):
            proj = self.videos.get_project(pid)
            if proj is not None:
                return pid
            raise ProjectNotFound(f"project or channel {pid!r} not found")
        return pid

    def add_tag(self, project_id: str, asset_id: str, tag: str) -> list[str]:
        pid = self.resolve_project_id(project_id)
        return self.assets.add_asset_tag(asset_id, tag, project_id=pid)

    def remove_tag(self, project_id: str, asset_id: str, tag: str) -> list[str]:
        pid = self.resolve_project_id(project_id)
        return self.assets.remove_asset_tag(asset_id, tag, project_id=pid)

    def list_tags(self, project_id: str, asset_id: str) -> list[str]:
        pid = self.resolve_project_id(project_id)
        return self.assets.list_asset_tags(asset_id, project_id=pid)


class SearchProjectAssets:
    """Busca paginada e filtrada de assets no acervo do canal/projeto."""

    def __init__(
        self,
        videos: VideoRepository,
        assets: AssetRepository,
        channels: ChannelProfileRepository | None = None,
    ):
        self.videos, self.assets, self.channels = videos, assets, channels

    def resolve_project_id(self, project_or_channel_id: str) -> str:
        pid = check_id(project_or_channel_id)
        if hasattr(self.videos, "get_project"):
            proj = self.videos.get_project(pid)
            if proj is not None:
                return pid
        if self.channels is not None:
            profile = self.channels.get(pid)
            if profile is not None:
                return profile.project_id
        if hasattr(self.videos, "get_project"):
            proj = self.videos.get_project(pid)
            if proj is not None:
                return pid
            raise ProjectNotFound(f"project or channel {pid!r} not found")
        return pid

    def execute(
        self,
        project_id: str,
        *,
        query: str | None = None,
        tag: str | None = None,
        kind: str | None = None,
        license: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Asset], int]:
        pid = self.resolve_project_id(project_id)
        return self.assets.search_project_assets(
            project_id=pid,
            query=query,
            tag=tag,
            kind=kind,
            license=license,
            limit=limit,
            offset=offset,
        )


@dataclass(frozen=True)
class Media:
    storyboard: PrepareStoryboard
    produce: ProduceAssets
    list_assets: ListAssets
    list_candidates: "ListSceneCandidates | None" = None
    swap: "SwapSceneMedia | None" = None
    broll: "SetSceneBroll | None" = None
    asset_file: "SceneAssetFile | None" = None
    import_media: "ImportExternalMedia | None" = None
    direct_asset_file: "AssetFile | None" = None
    scene_timing: "GetSceneTiming | None" = None
    manage_tags: "ManageAssetTags | None" = None
    search_assets: "SearchProjectAssets | None" = None
