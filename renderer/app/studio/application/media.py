"""Casos de uso de mídia: storyboard e produção de imagens por cena (cache por conteúdo, licença obrigatória)."""
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from ..domain.contracts import Asset, AssetKind, Scene, Video, VideoStatus
from ..domain.ids import asset_cache_key
from ..domain.media import ASPECT_FOR, build_image_prompt, strip_style
from ..domain.media_ranker import MediaRanker
from .budget import PaidOperationGuard, paid_key, provider_settlement
from .editorial import CostGuard, StateConflict, _require_video
from .errors import ServiceUnavailable
from .ports import (AssetRepository, AssetStore, ImageModel, MediaCandidate, MediaFetcher, MediaSearch, ProductionLock,
                    ScriptRepository, UsageRepository, VideoRepository)

ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}


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

    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, search: MediaSearch):
        self.videos, self.scripts, self.search = videos, scripts, search

    def execute(self, video_id: str, scene_id: str, *, per_page: int = 10,
                media_type: str = "image") -> SceneCandidates:
        video = _require_video(self.videos, video_id)
        scene = _scene(self.scripts, video_id, scene_id)
        if self.search is None:
            raise ServiceUnavailable("media search is not configured")
        query = strip_style(scene.image_prompt).strip() or scene.caption.strip()
        if not query:
            return SceneCandidates(scene_id=scene.id, query="", candidates=())
        orientation = "portrait" if ASPECT_FOR[video.format] == "9:16" else "landscape"
        found = self.search.search(query, media_type=media_type, orientation=orientation, per_page=per_page)
        if not found:
            return SceneCandidates(scene_id=scene.id, query=query, candidates=())

        target_format = video.format.value if hasattr(video.format, "value") else str(video.format)
        visual_intent = getattr(scene, "visual_intent", "")
        queries = [query]
        scene_queries = getattr(scene, "search_queries", None)
        if scene_queries:
            for sq in scene_queries:
                if sq and sq not in queries:
                    queries.append(sq)

        ranked = MediaRanker.rank(
            found,
            visual_intent=visual_intent,
            queries=queries,
            target_format=target_format,
        )
        ranked_candidates = tuple(sc.candidate for sc in ranked)
        return SceneCandidates(scene_id=scene.id, query=query, candidates=ranked_candidates)


@dataclass(frozen=True)
class SceneMediaResult:
    """Resultado da troca: asset final da cena e se houve escrita (``changed``); ``reason`` explica o no-op."""

    scene_id: str
    asset: Asset | None
    changed: bool
    reason: str = ""


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
                expected_version: int | None = None) -> SceneMediaResult:
        video = _require_video(self.videos, video_id)
        scene = _scene(self.scripts, video_id, scene_id)
        if expected_version is not None:
            latest = self.scripts.latest(video_id)
            if latest is None or latest.version != expected_version:
                raise StateConflict("script version changed underneath the media swap")
        if asset_id is None and candidate is None:
            current = self.assets.get(scene.asset_id) if scene.asset_id else None
            return SceneMediaResult(scene_id=scene.id, asset=current, changed=False, reason="no_candidate")
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
        if scene.asset_id == asset.id:
            return SceneMediaResult(scene_id=scene.id, asset=asset, changed=False, reason="already-linked")
        if expected_asset_id is not None and (scene.asset_id or "") != expected_asset_id:
            raise StateConflict("scene media changed underneath; reload before swapping")
        if not self.assets.swap_scene_asset(video_id, scene.id, asset.id, expected_asset_id=scene.asset_id):
            raise StateConflict("scene media changed underneath; nothing was written")
        return SceneMediaResult(scene_id=scene.id, asset=asset, changed=True)

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
        key = asset_cache_key("image", provider, candidate.media_id or candidate.url, candidate.url, {"aspect": aspect})
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


@dataclass(frozen=True)
class Media:
    storyboard: PrepareStoryboard
    produce: ProduceAssets
    list_assets: ListAssets
    list_candidates: "ListSceneCandidates | None" = None
    swap: "SwapSceneMedia | None" = None
    broll: "SetSceneBroll | None" = None
    asset_file: "SceneAssetFile | None" = None
