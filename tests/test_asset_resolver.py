"""RP-019..RP-022 — Asset Resolver e multi-asset (fatia 5 do Render Plan).

Cobre a porta ``AssetResolver`` (``application/ports.py``), o domínio puro
(``domain/asset_resolver.py``: ``AssetDescriptor``, ``AssetManifest``,
``verify_descriptor``, ``check_fit``), o caso de uso ``ResolvePlanAssets`` e o adapter
``LocalAssetResolver`` (disco, sem FFmpeg/subprocess).

Aceite de RP-04 (design R1/C4): **uma cena suporta múltiplos shots com mídias
distintas** — imagem, vídeo, gráfico e texto local — cada um resolvido e validado pelo
tipo. A sondagem de vídeo (ffprobe) é do executor (RP-05); aqui o vídeo é declarado.
"""
import hashlib
import sys
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.asset_resolver import LocalAssetResolver  # noqa: E402
from app.studio.application.assets import ResolvePlanAssets, ResolvedAssets  # noqa: E402
from app.studio.domain.asset_resolver import (  # noqa: E402
    AssetDescriptor,
    AssetManifest,
    AssetResolutionError,
    check_fit,
    verify_descriptor,
)
from app.studio.domain.contracts import VideoFormat  # noqa: E402
from app.studio.domain.render_plan import (  # noqa: E402
    AssetReference,
    Composition,
    Output,
    Provenance,
    RenderPlan,
    Scene,
    Shot,
    StyleSnapshot,
    Timebase,
    Timeline,
    Track,
)

SH = {name: hashlib.sha256(name.encode("utf-8")).hexdigest() for name in ("image", "video", "graphic", "text")}

TECH = {
    "image": dict(codec="png", width=1080, height=1920),
    "graphic": dict(codec="png", width=1080, height=1920),
    "video": dict(codec="h264", width=1080, height=1920, duration_ticks=300),
    "text": dict(),
}

VIDEO_META = {"codec": "h264", "width": "1080", "height": "1920", "duration_ticks": "300"}


# --------------------------------------------------------------------------- #
# Construtores
# --------------------------------------------------------------------------- #

def reference(asset_id="asset-image", media_type="image", *, sha=None, uri=None, license="CC0", **overrides):
    data = dict(asset_id=asset_id, asset_version=1, uri=uri or f"storage/{asset_id}.bin",
                content_sha256=sha or SH[media_type], media_type=media_type, license=license)
    data.update(overrides)
    return AssetReference(**data)


def descriptor(ref, **overrides):
    data = dict(asset_id=ref.asset_id, asset_version=ref.asset_version, uri=ref.uri,
                content_sha256=ref.content_sha256, media_type=ref.media_type, license=ref.license,
                available=True, **TECH[ref.media_type])
    data.update(overrides)
    return AssetDescriptor(**data)


def multi_media_plan():
    """Uma cena, quatro shots contíguos com mídias distintas (aceite de RP-04)."""
    refs = [
        reference("asset-image", "image", uri="storage/image.png"),
        reference("asset-video", "video", uri="storage/video.mp4", metadata=dict(VIDEO_META)),
        reference("asset-graphic", "graphic", uri="storage/graphic.png"),
        reference("asset-text", "text", uri="text:scene-01", license=None),
    ]
    shots = [
        Shot(shot_id="s1", track_id="visual-main", start_tick=0, duration_ticks=60, asset_ref="asset-image"),
        Shot(shot_id="s2", track_id="visual-main", start_tick=60, duration_ticks=60, asset_ref="asset-video"),
        Shot(shot_id="s3", track_id="visual-main", start_tick=120, duration_ticks=60, asset_ref="asset-graphic"),
        Shot(shot_id="s4", track_id="visual-main", start_tick=180, duration_ticks=70, asset_ref="asset-text"),
    ]
    return RenderPlan(
        plan_id="plan-01", revision=1, project_id="project-01", video_id="video-01",
        output=Output(format=VideoFormat.short, width=1080, height=1920),
        timeline=Timeline(timebase=Timebase(ticks_per_second=25),
                          tracks=[Track(track_id="visual-main", kind="visual")],
                          scenes=[Scene(scene_id="scene-01", start_tick=0, duration_ticks=250, shots=shots)]),
        asset_manifest=refs,
        style_snapshot=StyleSnapshot(style_id="channel-01", version=1),
        provenance=Provenance(builder_version="1.0.0"),
    )


class FakeResolver:
    def __init__(self, descriptors):
        self.by_id = {d.asset_id: d for d in descriptors}

    def resolve(self, ref):
        return self.by_id[ref.asset_id]


def write_png(root: Path, rel: str, size=(1080, 1920)) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (10, 20, 30)).save(path, "PNG")
    return path


def sha_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# RP-021 — AssetDescriptor por tipo de mídia
# --------------------------------------------------------------------------- #

def test_descriptor_requires_a_license_for_external_media():
    with pytest.raises(ValidationError, match="license"):
        descriptor(reference("a", "image"), license=None)


@pytest.mark.parametrize("media_type", ["image", "graphic", "video"])
def test_descriptor_requires_codec_and_resolution_for_raster_media(media_type):
    with pytest.raises(ValidationError, match="codec"):
        descriptor(reference("a", media_type), codec="rot13")
    with pytest.raises(ValidationError, match="width|resolution"):
        descriptor(reference("a", media_type), width=None)


def test_descriptor_image_has_no_duration_and_video_requires_it():
    with pytest.raises(ValidationError, match="duration"):
        descriptor(reference("a", "image"), duration_ticks=25)
    with pytest.raises(ValidationError, match="duration"):
        descriptor(reference("a", "video"), duration_ticks=None)


def test_descriptor_video_rejects_an_unknown_codec():
    with pytest.raises(ValidationError, match="codec"):
        descriptor(reference("a", "video"), codec="raw")


def test_local_text_asset_is_exempt_from_external_media():
    # text_animation é local: sem codec, resolução, duração nem localização (RP-021).
    text = descriptor(reference("a", "text", license=None))
    assert (text.codec, text.width, text.height, text.duration_ticks, text.location) == (None, None, None, None, "")
    with pytest.raises(ValidationError, match="codec|resolution|duration"):
        descriptor(reference("a", "text", license=None), codec="png")
    with pytest.raises(ValidationError, match="location"):
        descriptor(reference("a", "text", license=None), location="storage/a.png")


def test_unavailable_descriptor_may_omit_the_unknown_technical_metadata():
    missing = AssetDescriptor(asset_id="a", asset_version=1, uri="storage/a.png",
                              content_sha256=SH["image"], media_type="image",
                              license="CC0", available=False, location="storage/a.png")
    assert missing.codec is None and missing.width is None and missing.available is False


def test_descriptor_is_frozen_and_forbids_extra_fields():
    d = descriptor(reference("a", "image"))
    with pytest.raises(Exception):
        d.codec = "jpeg"
    with pytest.raises(ValidationError):
        descriptor(reference("a", "image"), surprise=1)


# --------------------------------------------------------------------------- #
# RP-020 — AssetManifest (URI, versão, hash e licença)
# --------------------------------------------------------------------------- #

def test_manifest_indexes_references_and_rejects_duplicates():
    manifest = AssetManifest(references=(reference("a", "image"), reference("b", "video")))
    assert len(manifest) == 2 and manifest.get("a").media_type == "image" and manifest.get("ghost") is None
    assert "b" in manifest
    with pytest.raises(ValidationError, match="duplicate"):
        AssetManifest(references=(reference("a", "image"), reference("a", "image")))


def test_manifest_of_plan_mirrors_the_plan_manifest():
    manifest = AssetManifest.of(multi_media_plan())
    assert set(manifest.by_id) == {"asset-image", "asset-video", "asset-graphic", "asset-text"}


# --------------------------------------------------------------------------- #
# RP-019/RP-020 — verify_descriptor contra o manifesto
# --------------------------------------------------------------------------- #

def test_verify_descriptor_accepts_a_matching_descriptor():
    ref = reference("a", "image")
    verify_descriptor(AssetManifest(references=(ref,)), descriptor(ref))


def test_verify_descriptor_rejects_an_unknown_asset():
    manifest = AssetManifest(references=(reference("a", "image"),))
    with pytest.raises(AssetResolutionError, match="not declared"):
        verify_descriptor(manifest, descriptor(reference("ghost", "image")))


@pytest.mark.parametrize("field,value", [
    ("asset_version", 2),
    ("uri", "storage/other.png"),
    ("content_sha256", "f" * 64),
    ("media_type", "graphic"),
])
def test_verify_descriptor_rejects_identity_drift(field, value):
    ref = reference("a", "image")
    manifest = AssetManifest(references=(ref,))
    with pytest.raises(AssetResolutionError, match=field):
        verify_descriptor(manifest, descriptor(ref, **{field: value}))


def test_verify_descriptor_rejects_a_license_mismatch():
    ref = reference("a", "image", license="CC0")
    with pytest.raises(AssetResolutionError, match="license"):
        verify_descriptor(AssetManifest(references=(ref,)), descriptor(ref, license="Proprietary"))


def test_verify_descriptor_rejects_an_unavailable_asset():
    ref = reference("a", "image")
    unavailable = AssetDescriptor(asset_id="a", asset_version=1, uri=ref.uri,
                                  content_sha256=ref.content_sha256, media_type="image",
                                  license="CC0", available=False, location="storage/a.png")
    with pytest.raises(AssetResolutionError, match="not available"):
        verify_descriptor(AssetManifest(references=(ref,)), unavailable)


# --------------------------------------------------------------------------- #
# RP-022 — check_fit (resolução e duração)
# --------------------------------------------------------------------------- #

def test_check_fit_rejects_upscaling_under_cover():
    out = Output(format=VideoFormat.short, width=1080, height=1920)
    with pytest.raises(AssetResolutionError, match="upscale|smaller"):
        check_fit(descriptor(reference("a", "image"), width=540, height=960), out)
    check_fit(descriptor(reference("a", "image"), width=1080, height=1920), out)  # exato
    check_fit(descriptor(reference("a", "image"), width=2160, height=3840), out)  # maior


def test_check_fit_allows_a_smaller_asset_under_contain():
    out = Output(format=VideoFormat.short, width=1080, height=1920)
    check_fit(descriptor(reference("a", "image"), width=540, height=960), out, fit="contain")


def test_check_fit_rejects_a_video_shorter_than_its_shot():
    out = Output(format=VideoFormat.short, width=1080, height=1920)
    with pytest.raises(AssetResolutionError, match="shorter"):
        check_fit(descriptor(reference("a", "video"), duration_ticks=50), out, shot_duration_ticks=60)
    check_fit(descriptor(reference("a", "video"), duration_ticks=60), out, shot_duration_ticks=60)
    check_fit(descriptor(reference("a", "video"), duration_ticks=300), out, shot_duration_ticks=60)


def test_check_fit_ignores_resolution_and_duration_for_the_local_text_asset():
    out = Output(format=VideoFormat.short, width=1080, height=1920)
    check_fit(descriptor(reference("a", "text", license=None)), out, shot_duration_ticks=250)


# --------------------------------------------------------------------------- #
# RP-019/RP-022 — caso de uso ResolvePlanAssets
# --------------------------------------------------------------------------- #

def test_resolve_plan_returns_a_descriptor_per_manifest_entry():
    plan = multi_media_plan()
    resolver = FakeResolver([descriptor(ref) for ref in plan.asset_manifest])
    result = ResolvePlanAssets(resolver).execute(plan)
    assert isinstance(result, ResolvedAssets)
    assert {d.asset_id for d in result.descriptors} == {"asset-image", "asset-video", "asset-graphic", "asset-text"}


def test_resolve_plan_accepts_a_multi_shot_scene_with_distinct_media():
    plan = multi_media_plan()
    resolver = FakeResolver([descriptor(ref) for ref in plan.asset_manifest])
    result = ResolvePlanAssets(resolver).execute(plan)
    assert [result.get(a).media_type for a in ("asset-image", "asset-video", "asset-graphic", "asset-text")] == \
        ["image", "video", "graphic", "text"]
    assert result.get("asset-video").duration_ticks == 300
    assert result.get("asset-image").width == 1080 and result.get("asset-image").height == 1920


def test_resolve_plan_fails_when_an_asset_is_unavailable():
    plan = multi_media_plan()
    refs = {r.asset_id: r for r in plan.asset_manifest}
    missing = AssetDescriptor(asset_id="asset-graphic", asset_version=1, uri=refs["asset-graphic"].uri,
                              content_sha256=refs["asset-graphic"].content_sha256, media_type="graphic",
                              license="CC0", available=False, location="storage/graphic.png")
    resolver = FakeResolver([descriptor(r) if r.asset_id != "asset-graphic" else missing for r in plan.asset_manifest])
    with pytest.raises(AssetResolutionError, match="not available"):
        ResolvePlanAssets(resolver).execute(plan)


def test_resolve_plan_fails_when_the_resolver_returns_another_asset():
    plan = multi_media_plan()
    # descriptor do asset-image com o hash de outro conteúdo: identidade não confere com o manifesto
    swapped = descriptor(reference("asset-image", "image", uri="storage/image.png"), content_sha256="0" * 64)
    resolver = FakeResolver([swapped] + [descriptor(r) for r in plan.asset_manifest if r.asset_id != "asset-image"])
    with pytest.raises(AssetResolutionError, match="content_sha256"):
        ResolvePlanAssets(resolver).execute(plan)


def test_resolve_plan_fails_when_the_video_is_shorter_than_its_shot():
    plan = multi_media_plan()  # o shot do vídeo dura 60 ticks
    shortened = [descriptor(r, duration_ticks=25) if r.asset_id == "asset-video" else descriptor(r)
                 for r in plan.asset_manifest]
    with pytest.raises(AssetResolutionError, match="shorter"):
        ResolvePlanAssets(FakeResolver(shortened)).execute(plan)


def test_resolve_plan_honours_contain_on_a_small_image():
    plan = multi_media_plan()
    small = [descriptor(r, width=540, height=960) if r.asset_id == "asset-image" else descriptor(r)
             for r in plan.asset_manifest]
    with pytest.raises(AssetResolutionError, match="upscale"):
        ResolvePlanAssets(FakeResolver(small)).execute(plan)
    # com composition=contain o mesmo asset pequeno é aceito (letterbox, sem upscale obrigatório)
    composed = multi_media_plan()
    shots = list(composed.timeline.scenes[0].shots)
    shots[0] = shots[0].model_copy(update={"composition": Composition(fit="contain")})
    contained = composed.model_copy(update={
        "timeline": composed.timeline.model_copy(update={
            "scenes": [composed.timeline.scenes[0].model_copy(update={"shots": shots})]})})
    result = ResolvePlanAssets(FakeResolver(small)).execute(contained)
    assert result.get("asset-image").width == 540


# --------------------------------------------------------------------------- #
# Adapter — LocalAssetResolver (disco real, sem FFmpeg/subprocess)
# --------------------------------------------------------------------------- #

def test_adapter_probes_a_real_image_and_verifies_its_hash(tmp_path):
    path = write_png(tmp_path, "storage/image.png")
    ref = reference("asset-image", "image", uri="storage/image.png", sha=sha_of(path))
    d = LocalAssetResolver(tmp_path).resolve(ref)
    assert (d.available, d.codec, d.width, d.height) == (True, "png", 1080, 1920)
    assert d.byte_size == path.stat().st_size and d.duration_ticks is None


def test_adapter_rejects_a_content_hash_mismatch(tmp_path):
    write_png(tmp_path, "storage/image.png")
    ref = reference("asset-image", "image", uri="storage/image.png", sha="0" * 64)
    with pytest.raises(AssetResolutionError, match="content hash"):
        LocalAssetResolver(tmp_path).resolve(ref)


def test_adapter_reports_an_unavailable_asset_without_inventing_metadata(tmp_path):
    ref = reference("asset-image", "image", uri="storage/missing.png", sha=SH["image"])
    d = LocalAssetResolver(tmp_path).resolve(ref)
    assert d.available is False and d.codec is None and d.width is None and d.location == "storage/missing.png"


def test_adapter_rejects_external_media_without_a_registered_license(tmp_path):
    path = write_png(tmp_path, "storage/image.png")
    ref = reference("asset-image", "image", uri="storage/image.png", sha=sha_of(path), license=None)
    with pytest.raises(AssetResolutionError, match="license"):
        LocalAssetResolver(tmp_path).resolve(ref)


def test_adapter_rejects_a_file_that_is_not_a_readable_image(tmp_path):
    path = tmp_path / "storage" / "image.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"definitely not an image")
    ref = reference("asset-image", "image", uri="storage/image.png", sha=sha_of(path))
    with pytest.raises(AssetResolutionError, match="readable image"):
        LocalAssetResolver(tmp_path).resolve(ref)


def test_adapter_resolves_a_video_from_declared_metadata(tmp_path):
    path = tmp_path / "storage" / "video.mp4"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"mp4-bytes")
    ref = reference("asset-video", "video", uri="storage/video.mp4", sha=sha_of(path), metadata=dict(VIDEO_META))
    d = LocalAssetResolver(tmp_path).resolve(ref)
    assert (d.available, d.codec, d.width, d.height, d.duration_ticks) == (True, "h264", 1080, 1920, 300)
    assert d.byte_size == len(b"mp4-bytes")


def test_adapter_rejects_a_video_without_declared_metadata(tmp_path):
    path = tmp_path / "storage" / "video.mp4"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"mp4-bytes")
    ref = reference("asset-video", "video", uri="storage/video.mp4", sha=sha_of(path))
    with pytest.raises(AssetResolutionError, match="declared metadata"):
        LocalAssetResolver(tmp_path).resolve(ref)


def test_adapter_rejects_an_unknown_declared_video_codec(tmp_path):
    path = tmp_path / "storage" / "video.mp4"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"mp4-bytes")
    bad = {**VIDEO_META, "codec": "raw"}
    ref = reference("asset-video", "video", uri="storage/video.mp4", sha=sha_of(path), metadata=bad)
    with pytest.raises(AssetResolutionError, match="codec"):
        LocalAssetResolver(tmp_path).resolve(ref)


def test_adapter_rejects_a_uri_that_escapes_the_root(tmp_path):
    ref = reference("asset-image", "image", uri="../outside.png", sha=SH["image"])
    with pytest.raises(AssetResolutionError, match="escapes"):
        LocalAssetResolver(tmp_path).resolve(ref)


def test_adapter_resolves_a_local_text_asset_without_external_media(tmp_path):
    ref = reference("asset-text", "text", uri="text:scene-01", license=None)
    d = LocalAssetResolver(tmp_path).resolve(ref)
    assert (d.available, d.media_type, d.location, d.codec) == (True, "text", "", None)


def test_adapter_and_use_case_resolve_a_multi_media_scene_from_disk(tmp_path):
    """Aceite de RP-04 ponta a ponta: cena de quatro shots com mídias distintas no disco."""
    image = write_png(tmp_path, "storage/image.png")
    graphic = write_png(tmp_path, "storage/graphic.png")
    video = tmp_path / "storage" / "video.mp4"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"mp4-bytes")
    refs = [
        reference("asset-image", "image", uri="storage/image.png", sha=sha_of(image)),
        reference("asset-video", "video", uri="storage/video.mp4", sha=sha_of(video), metadata=dict(VIDEO_META)),
        reference("asset-graphic", "graphic", uri="storage/graphic.png", sha=sha_of(graphic)),
        reference("asset-text", "text", uri="text:scene-01", license=None),
    ]
    plan = multi_media_plan().model_copy(update={"asset_manifest": refs})

    result = ResolvePlanAssets(LocalAssetResolver(tmp_path)).execute(plan)

    assert {a: result.get(a).media_type for a in ("asset-image", "asset-video", "asset-graphic", "asset-text")} == {
        "asset-image": "image", "asset-video": "video", "asset-graphic": "graphic", "asset-text": "text"}
    assert result.get("asset-image").location == "storage/image.png"
    assert result.get("asset-image").codec == "png"
    assert result.get("asset-video").duration_ticks == 300
