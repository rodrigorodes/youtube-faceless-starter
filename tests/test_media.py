import contextlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.editorial import CostGuard, StateConflict, VideoNotFound  # noqa: E402
from app.studio.application.media import (  # noqa: E402
    AssetRefused, ListAssets, PrepareStoryboard, ProduceAssets,
)
from app.studio.application.ports import ImageResult, ModelUnavailable  # noqa: E402
from app.studio.domain.contracts import Asset, Scene, UsageEntry, Video, VideoFormat, VideoStatus  # noqa: E402
from app.studio.domain.media import IMAGE_STYLE  # noqa: E402
from app.studio.domain.policy import CostRefused  # noqa: E402

S = VideoStatus
V, P = "v" * 32, "p" * 32


class Videos:
    def __init__(self, status=S.FACT_CHECKED, fmt=VideoFormat.short):
        self.status, self.fmt, self.exists = status, fmt, True

    def get_video(self, video_id):
        return Video(id=V, project_id=P, topic="ADE 2026", format=self.fmt, status=self.status) if self.exists else None

    def transition_video(self, video_id, expected, new):
        if self.status != expected:
            return False
        self.status = new
        return True


class Scripts:
    def __init__(self, assets, prompts=("wide stage with colorful lights", "crowd silhouettes under neon lights", "aerial city canals at night")):
        self.assets = assets
        self.prompts = list(prompts)

    def scenes(self, video_id):
        return [Scene(id=f"{i:032x}", video_id=V, idx=i, narration=f"Narração {i} válida", image_prompt=p, claim_ids=["c"],
                      asset_id=self.assets.links.get(i)) for i, p in enumerate(self.prompts)]


class Assets:
    def __init__(self):
        self.by_key, self.by_id, self.links = {}, {}, {}
        self.link_calls, self.refuse_link = [], False

    def find(self, cache_key):
        return self.by_key.get(cache_key)

    def add(self, asset):
        existing = self.by_key.get(asset.cache_key)
        if existing:
            return existing
        self.by_key[asset.cache_key] = self.by_id[asset.id] = asset
        return asset

    def get(self, asset_id):
        return self.by_id.get(asset_id)

    def link_scene(self, video_id, idx, asset_id, image_prompt):
        self.link_calls.append((idx, image_prompt))
        if self.refuse_link:
            return False
        self.links[idx] = asset_id
        return True


class Store:
    def __init__(self):
        self.puts, self.fail = [], False

    def put(self, cache_key, data, aspect):
        if self.fail:
            raise AssetRefused("not a valid image")
        self.puts.append((cache_key, aspect))
        return f"cache/{cache_key[:2]}/{cache_key}.png"


class Lock:
    def __init__(self, free=True):
        self.free, self.held = free, 0

    @contextlib.contextmanager
    def hold(self, video_id):
        if self.free:
            self.held += 1
        yield self.free


class Usage:
    def __init__(self):
        self.entries = []

    def record(self, video_id, entry):
        self.entries.append(entry)

    def spent_video(self, video_id):
        return sum(e.cost_usd for e in self.entries)

    def spent_month(self):
        return 0.0


class Image:
    name, model = "fake", "m:free"

    def __init__(self, license="ai-generated:m", cost=0.0, mime="image/png", fail_on=()):
        self.license, self.cost, self.mime, self.fail_on = license, cost, mime, set(fail_on)
        self.calls, self.prompts, self.aspects = 0, [], []

    def cost_estimate(self, prompt):
        return self.cost

    def generate(self, prompt, *, aspect="9:16"):
        self.calls += 1
        if self.calls in self.fail_on:
            raise ModelUnavailable("down")
        self.prompts.append(prompt)
        self.aspects.append(aspect)
        return ImageResult(data=b"img", mime=self.mime, usage=UsageEntry(step="image", provider="fake", model="m:free", cost_usd=self.cost),
                           license=self.license, attribution="Foto de Fulano", source_url="https://x.example/p")


def world(status=S.STORYBOARDED, **kw):
    assets = Assets()
    return {"videos": Videos(status, **kw), "assets": assets, "scripts": Scripts(assets), "store": Store(), "usage": Usage(), "lock": Lock()}


def producer(w, image, cap_video=0.0):
    return ProduceAssets(w["videos"], w["scripts"], w["assets"], w["store"], CostGuard(w["usage"], cap_video, 15.0), w["usage"],
                        image_for=lambda project_id: image, lock=w["lock"])


# ---------- storyboard ----------
def test_storyboard_moves_fact_checked_to_storyboarded():
    w = world(S.FACT_CHECKED)
    PrepareStoryboard(w["videos"], w["scripts"]).execute(V)
    assert w["videos"].status == S.STORYBOARDED


@pytest.mark.parametrize("status", [S.IDEA, S.SCRIPTED, S.STORYBOARDED, S.ASSETS_READY])
def test_storyboard_needs_fact_checked(status):
    w = world(status)
    with pytest.raises(StateConflict):
        PrepareStoryboard(w["videos"], w["scripts"]).execute(V)
    assert w["videos"].status == status


def test_storyboard_unknown_video_and_no_scenes():
    w = world(S.FACT_CHECKED)
    w["scripts"].prompts = []
    with pytest.raises(StateConflict, match="scenes"):
        PrepareStoryboard(w["videos"], w["scripts"]).execute(V)
    w["videos"].exists = False
    with pytest.raises(VideoNotFound):
        PrepareStoryboard(w["videos"], w["scripts"]).execute(V)


# ---------- produção ----------
def test_one_asset_per_scene_linked_usage_recorded_and_state_advances():
    w, img = world(), Image()
    result = producer(w, img).execute(V)
    assert (result.generated, result.reused) == (3, 0) and img.calls == 3
    assert sorted(w["assets"].links) == [0, 1, 2] and w["videos"].status == S.ASSETS_READY
    assert len(w["usage"].entries) == 3
    asset = w["assets"].get(w["assets"].links[0])
    assert asset.license == "ai-generated:m" and asset.attribution == "Foto de Fulano" and asset.source_url == "https://x.example/p"
    assert asset.path.startswith("cache/") and asset.provider == "fake" and asset.kind.value == "image"


def test_style_is_appended_and_aspect_follows_the_format():
    w, img = world(), Image()
    producer(w, img).execute(V)
    assert all(p.endswith(IMAGE_STYLE["9:16"]) for p in img.prompts) and set(img.aspects) == {"9:16"}
    w2, img2 = world(fmt=VideoFormat.long), Image()
    producer(w2, img2).execute(V)
    assert set(img2.aspects) == {"16:9"} and all(p.endswith(IMAGE_STYLE["16:9"]) for p in img2.prompts)
    assert set(w["assets"].by_key).isdisjoint(w2["assets"].by_key)  # aspecto diferente, chave diferente


def test_same_prompt_in_two_scenes_generates_once():
    w, img = world(), Image()
    w["scripts"].prompts = ["wide stage with colorful lights"] * 3
    result = producer(w, img).execute(V)
    assert img.calls == 1 and (result.generated, result.reused) == (1, 2)
    assert len(set(w["assets"].links.values())) == 1


def test_second_render_of_the_same_content_generates_zero_new_images():
    first, img = world(), Image()
    producer(first, img).execute(V)
    again = world()
    again["assets"] = first["assets"]  # o cache é global; outro vídeo com os mesmos prompts
    again["scripts"] = Scripts(again["assets"])
    again["assets"].links.clear()
    result = producer(again, img).execute(V)
    assert img.calls == 3 and (result.generated, result.reused) == (0, 3) and again["videos"].status == S.ASSETS_READY


def test_partial_failure_resumes_and_only_generates_what_is_missing():
    w, flaky = world(), Image(fail_on={3})
    with pytest.raises(ModelUnavailable):
        producer(w, flaky).execute(V)
    assert sorted(w["assets"].links) == [0, 1] and w["videos"].status == S.STORYBOARDED
    healthy = Image()
    result = producer(w, healthy).execute(V)
    assert healthy.calls == 1 and (result.generated, result.reused) == (1, 0) and w["videos"].status == S.ASSETS_READY


@pytest.mark.parametrize("license", ["", "   ", "\n"])
def test_asset_without_license_is_refused_and_nothing_is_stored_or_linked(license):
    w, img = world(), Image(license=license)
    with pytest.raises(AssetRefused, match="license"):
        producer(w, img).execute(V)
    assert w["store"].puts == [] and w["assets"].by_key == {} and w["assets"].links == {} and w["videos"].status == S.STORYBOARDED
    assert len(w["usage"].entries) == 1  # a chamada aconteceu e foi contabilizada


@pytest.mark.parametrize("mime", ["text/html", "application/pdf", "image/svg+xml", ""])
def test_non_raster_mime_is_refused(mime):
    w = world()
    with pytest.raises(AssetRefused, match="mime"):
        producer(w, Image(mime=mime)).execute(V)
    assert w["store"].puts == []


def test_store_rejection_leaves_no_asset():
    w = world()
    w["store"].fail = True
    with pytest.raises(AssetRefused):
        producer(w, Image()).execute(V)
    assert w["assets"].by_key == {} and w["assets"].links == {}


def test_paid_provider_such_as_veo_is_refused_before_any_call_with_cap_zero():
    w, veo = world(), Image(cost=3.2)
    with pytest.raises(CostRefused):
        producer(w, veo, cap_video=0.0).execute(V)
    assert veo.calls == 0 and w["usage"].entries == [] and w["videos"].status == S.STORYBOARDED
    with pytest.raises(CostRefused):  # liberado por vídeo, mas estoura o teto
        producer(w, veo, cap_video=3.0).execute(V)
    assert veo.calls == 0


def test_wrong_state_unknown_video_and_lost_race():
    for status in (S.IDEA, S.FACT_CHECKED, S.ASSETS_READY):
        w = world(status)
        with pytest.raises(StateConflict):
            producer(w, Image()).execute(V)
    w = world()
    w["videos"].exists = False
    with pytest.raises(VideoNotFound):
        producer(w, Image()).execute(V)
    w = world()
    img = Image()
    original = w["videos"].transition_video
    w["videos"].transition_video = lambda *a: (setattr(w["videos"], "status", S.FAILED), original(*a))[1]  # outro processo mudou o estado
    with pytest.raises(StateConflict):
        producer(w, img).execute(V)


def test_list_assets_returns_scene_with_asset():
    w = world()
    producer(w, Image()).execute(V)
    listed = ListAssets(w["videos"], w["scripts"], w["assets"]).execute(V)
    assert [x.idx for x in listed] == [0, 1, 2] and all(x.asset and x.asset.license for x in listed)


# ---------- achados da revisão ----------
def test_concurrent_production_for_the_same_video_is_refused_without_calling_the_provider():
    w, img = world(), Image()
    w["lock"].free = False
    with pytest.raises(StateConflict, match="in progress"):
        producer(w, img).execute(V)
    assert img.calls == 0 and w["usage"].entries == [] and w["videos"].status == S.STORYBOARDED


def test_lock_is_held_for_the_whole_run():
    w = world()
    producer(w, Image()).execute(V)
    assert w["lock"].held == 1


def test_link_refused_when_scene_changed_underneath_stops_without_advancing():
    w = world()
    w["assets"].refuse_link = True
    with pytest.raises(StateConflict, match="scenes changed"):
        producer(w, Image()).execute(V)
    assert w["videos"].status == S.STORYBOARDED and w["assets"].links == {}


def test_link_is_conditioned_on_the_scene_prompt():
    w = world()
    producer(w, Image()).execute(V)
    assert sorted(w["assets"].link_calls) == sorted(enumerate(w["scripts"].prompts))


def test_accumulated_per_video_cap_stops_the_third_paid_image():
    w, img = world(), Image(cost=0.05)
    with pytest.raises(CostRefused):
        producer(w, img, cap_video=0.10).execute(V)
    assert img.calls == 2 and len(w["usage"].entries) == 2 and sorted(w["assets"].links) == [0, 1]
    assert w["videos"].status == S.STORYBOARDED


def test_rejected_images_are_still_in_the_ledger():
    for kw in ({"license": ""}, {"mime": "text/html"}):
        w = world()
        with pytest.raises(AssetRefused):
            producer(w, Image(**kw)).execute(V)
        assert len(w["usage"].entries) == 1
    w = world()
    w["store"].fail = True
    with pytest.raises(AssetRefused):
        producer(w, Image()).execute(V)
    assert len(w["usage"].entries) == 1
