"""Casos de uso de mídia: storyboard e produção de imagens por cena (cache por conteúdo, licença obrigatória)."""
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from ..domain.contracts import Asset, AssetKind, VideoStatus
from ..domain.ids import asset_cache_key
from ..domain.media import ASPECT_FOR, build_image_prompt
from .editorial import CostGuard, StateConflict, _require_video
from .ports import AssetRepository, AssetStore, ImageModel, ScriptRepository, UsageRepository, VideoRepository

ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}


class AssetRefused(ValueError):
    """Imagem do provedor recusada (sem licença, tipo não raster ou arquivo inválido); nada é gravado nem vinculado."""


class PrepareStoryboard:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository):
        self.videos, self.scripts = videos, scripts

    def execute(self, video_id: str) -> None:
        video = _require_video(self.videos, video_id)
        if video.status != VideoStatus.FACT_CHECKED:
            raise StateConflict(f"storyboard needs state FACT_CHECKED, got {video.status.value}")
        if not self.scripts.scenes(video_id):
            raise AssetRefused("no scenes to storyboard")
        if not self.videos.transition_video(video_id, VideoStatus.FACT_CHECKED, VideoStatus.STORYBOARDED):
            raise StateConflict("video state changed during the storyboard")


@dataclass(frozen=True)
class ProduceResult:
    generated: int
    reused: int


class ProduceAssets:
    def __init__(self, videos: VideoRepository, scripts: ScriptRepository, assets: AssetRepository, store: AssetStore,
                 guard: CostGuard, usage: UsageRepository, image_for: Callable[[str], ImageModel]):
        self.videos, self.scripts, self.assets, self.store = videos, scripts, assets, store
        self.guard, self.usage, self.image_for = guard, usage, image_for

    def execute(self, video_id: str) -> ProduceResult:
        """Retomável: cena já vinculada é pulada; imagem já no cache é reaproveitada; só o que falta é gerado."""
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
            self.assets.link_scene(video_id, scene.idx, asset.id)
        if not self.videos.transition_video(video_id, VideoStatus.STORYBOARDED, VideoStatus.ASSETS_READY):
            raise StateConflict("video state changed during asset production")
        return ProduceResult(generated, reused)

    def _generate(self, video_id: str, model: ImageModel, prompt: str, aspect: str, key: str) -> Asset:
        self.guard.check(video_id, model.cost_estimate(prompt))  # antes da chamada
        result = model.generate(prompt, aspect=aspect)
        self.usage.record(video_id, result.usage)  # a chamada aconteceu: contabiliza mesmo se a imagem for recusada
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


@dataclass(frozen=True)
class Media:
    storyboard: PrepareStoryboard
    produce: ProduceAssets
    list_assets: ListAssets
