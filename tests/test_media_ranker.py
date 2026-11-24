import pytest
from app.studio.domain.contracts import VideoFormat
from app.studio.domain.media import MediaCandidate as DomainMediaCandidate
from app.studio.application.ports import MediaCandidate as PortMediaCandidate
from app.studio.domain.media_ranker import MediaRanker, ScoredCandidate


def _make_candidate(
    *,
    media_id: str = "media-1",
    media_type: str = "image",
    width: int | None = 1080,
    height: int | None = 1920,
    duration_s: float | None = None,
    tags: tuple[str, ...] = (),
    url: str = "https://cdn.example.com/asset-1.jpg",
    source_url: str = "https://example.com/photo/asset-1",
    license: str = "CC0",
    attribution: str = "Creator",
) -> DomainMediaCandidate:
    return DomainMediaCandidate(
        license=license,
        source_url=source_url,
        url=url,
        attribution=attribution,
        media_id=media_id,
        media_type=media_type,
        width=width,
        height=height,
        duration_s=duration_s,
        tags=tags,
    )


def test_media_candidate_reexported_in_ports():
    assert DomainMediaCandidate is PortMediaCandidate
    candidate = DomainMediaCandidate(
        license="CC0",
        source_url="https://example.com/1",
        url="https://example.com/1.jpg",
        attribution="Author",
        duration_s=12.5,
        tags=("tokyo", "cyberpunk"),
    )
    assert candidate.duration_s == 12.5
    assert candidate.tags == ("tokyo", "cyberpunk")


def test_orientation_scoring_short_format():
    vertical = _make_candidate(media_id="v", width=1080, height=1920)
    horizontal = _make_candidate(media_id="h", width=1920, height=1080)
    square = _make_candidate(media_id="s", width=1080, height=1080)
    no_dim = _make_candidate(media_id="n", width=None, height=None)

    results = MediaRanker.rank(
        [horizontal, vertical, square, no_dim],
        visual_intent="",
        queries=[],
        target_format="short",
    )
    score_by_id = {sc.candidate.media_id: sc.score for sc in results}
    # vertical: +30 (orientation) + 20 (res >= 1080) = 50
    # square: +30 (height >= width) + 20 (res >= 1080) = 50
    # horizontal: +0 (orientation) + 20 (res >= 1080) = 20
    # no_dim: 0
    assert score_by_id["v"] >= 50.0
    assert score_by_id["s"] >= 50.0
    assert score_by_id["h"] == 20.0
    assert score_by_id["n"] == 0.0

    # Also works with target_format="9:16" and VideoFormat.short
    results_916 = MediaRanker.rank([horizontal, vertical], visual_intent="", queries=[], target_format="9:16")
    assert results_916[0].candidate.media_id == "v"


def test_orientation_scoring_long_format():
    vertical = _make_candidate(media_id="v", width=1080, height=1920)
    horizontal = _make_candidate(media_id="h", width=1920, height=1080)

    results = MediaRanker.rank(
        [vertical, horizontal],
        visual_intent="",
        queries=[],
        target_format="long",
    )
    score_by_id = {sc.candidate.media_id: sc.score for sc in results}
    # horizontal: +30 (orientation) + 20 (resolution) = 50
    # vertical: +0 (orientation) + 20 (resolution) = 20
    assert score_by_id["h"] >= 50.0
    assert score_by_id["v"] == 20.0

    # Also works with target_format="16:9" and VideoFormat.long
    results_169 = MediaRanker.rank([vertical, horizontal], visual_intent="", queries=[], target_format="16:9")
    assert results_169[0].candidate.media_id == "h"


def test_resolution_scoring():
    full_hd = _make_candidate(media_id="fhd", width=1920, height=1080)
    four_k = _make_candidate(media_id="4k", width=3840, height=2160)
    seven_twenty = _make_candidate(media_id="720p", width=1280, height=720)
    no_dim = _make_candidate(media_id="none", width=None, height=None)

    results = MediaRanker.rank(
        [full_hd, four_k, seven_twenty, no_dim],
        visual_intent="",
        queries=[],
        target_format="long",
    )
    score_by_id = {sc.candidate.media_id: sc.score for sc in results}
    # min dimension >= 1080 gets +20
    assert score_by_id["fhd"] == 50.0  # +30 orientation + 20 resolution
    assert score_by_id["4k"] == 50.0   # +30 orientation + 20 resolution
    assert score_by_id["720p"] == 30.0 # +30 orientation + 0 resolution
    assert score_by_id["none"] == 0.0


def test_term_overlap_scoring():
    # 0 matches
    c_none = _make_candidate(media_id="c0", tags=("forest", "trees"), url="https://cdn.example.com/nature.jpg")
    # 1 match ("tokyo")
    c_one = _make_candidate(media_id="c1", tags=("tokyo", "asia"), url="https://cdn.example.com/travel.jpg")
    # 2 matches ("tokyo", "cyberpunk")
    c_two = _make_candidate(media_id="c2", tags=("tokyo", "cyberpunk"), url="https://cdn.example.com/future.jpg")
    # 3 matches ("tokyo", "cyberpunk", "night" via url)
    c_three = _make_candidate(
        media_id="c3",
        tags=("tokyo", "cyberpunk"),
        url="https://cdn.example.com/photos/night-city.jpg",
    )
    # 4+ matches (capped at 30 pts)
    c_four = _make_candidate(
        media_id="c4",
        tags=("tokyo", "cyberpunk", "futuristic", "neon"),
        url="https://cdn.example.com/photos/night-city.jpg",
    )

    queries = ["cyberpunk tokyo night neon futuristic"]
    results = MediaRanker.rank(
        [c_none, c_one, c_two, c_three, c_four],
        visual_intent="cyberpunk city scene",
        queries=queries,
        target_format="short",
    )
    score_by_id = {sc.candidate.media_id: sc.score for sc in results}
    # Base for all vertical 1080x1920: +30 (orientation) + 20 (res) = 50
    assert score_by_id["c0"] == 50.0
    assert score_by_id["c1"] == 60.0  # +10
    assert score_by_id["c2"] == 70.0  # +20
    assert score_by_id["c3"] == 80.0  # +30
    assert score_by_id["c4"] == 80.0  # +30 cap


def test_video_duration_scoring():
    v_long = _make_candidate(media_id="v_long", media_type="video", duration_s=10.0)
    v_short = _make_candidate(media_id="v_short", media_type="video", duration_s=3.0)
    v_no_dur = _make_candidate(media_id="v_no_dur", media_type="video", duration_s=None)
    img = _make_candidate(media_id="img", media_type="image", duration_s=1.0)

    results = MediaRanker.rank(
        [v_long, v_short, v_no_dur, img],
        visual_intent="",
        queries=[],
        target_format="short",
        min_duration_s=5.0,
    )
    score_by_id = {sc.candidate.media_id: sc.score for sc in results}
    # Base: 50.0 (30 orientation + 20 resolution)
    assert score_by_id["v_long"] == 70.0   # 50 + 20
    assert score_by_id["v_short"] == 20.0  # 50 - 30
    assert score_by_id["v_no_dur"] == 50.0 # no penalty / no bonus
    assert score_by_id["img"] == 50.0      # image is unaffected by video min_duration_s


def test_repetition_penalty():
    fresh = _make_candidate(media_id="asset-fresh")
    used = _make_candidate(media_id="asset-used")

    results = MediaRanker.rank(
        [fresh, used],
        visual_intent="",
        queries=[],
        target_format="short",
        used_media_ids={"asset-used", "other-asset"},
    )
    score_by_id = {sc.candidate.media_id: sc.score for sc in results}
    assert score_by_id["asset-fresh"] == 50.0
    assert score_by_id["asset-used"] == 0.0  # 50 - 50

    used_sc = next(sc for sc in results if sc.candidate.media_id == "asset-used")
    assert "repetition penalty: asset already used in video" in used_sc.reasons


def test_descending_sort_order():
    c_best = _make_candidate(
        media_id="best",
        tags=("robot", "future"),
        width=1080,
        height=1920,
    )
    c_mid = _make_candidate(
        media_id="mid",
        tags=(),
        width=1080,
        height=1920,
    )
    c_worst = _make_candidate(
        media_id="worst",
        tags=(),
        width=720,
        height=720,
    )

    results = MediaRanker.rank(
        [c_mid, c_worst, c_best],
        visual_intent="robot future",
        queries=["robot"],
        target_format="short",
    )
    assert [sc.candidate.media_id for sc in results] == ["best", "mid", "worst"]
    assert results[0].score > results[1].score > results[2].score


def test_media_candidate_duration_validation():
    with pytest.raises(ValueError, match="duration_s"):
        _make_candidate(duration_s=0)
    with pytest.raises(ValueError, match="duration_s"):
        _make_candidate(duration_s=-5.0)
    with pytest.raises(ValueError, match="duration_s"):
        _make_candidate(duration_s="ten")


def test_empty_candidates_returns_empty_list():
    assert MediaRanker.rank([], visual_intent="test", queries=["test"], target_format="short") == []


def test_video_format_enum_and_default_arguments():
    c_vert = _make_candidate(media_id="v", width=1080, height=1920)
    c_horiz = _make_candidate(media_id="h", width=1920, height=1080)

    # Calling with VideoFormat enum and omitting optional args
    res_short = MediaRanker.rank([c_vert, c_horiz], visual_intent="", target_format=VideoFormat.short)
    assert res_short[0].candidate.media_id == "v"

    res_long = MediaRanker.rank([c_vert, c_horiz], visual_intent="", target_format=VideoFormat.long)
    assert res_long[0].candidate.media_id == "h"


def test_accent_normalization_and_short_token_filtering():
    c = _make_candidate(
        media_id="c_accent",
        tags=("robo", "inteligencia"),
        url="https://example.com/ai-robot.jpg",
    )
    # "ai" has len 2 (< 3) -> should not count
    # "robô" has accent -> normalizes to "robo" and matches tag "robo" (+10 pts)
    res = MediaRanker.rank(
        [c],
        visual_intent="",
        queries=["ai robô"],
        target_format="short",
    )
    # Orientation 30 + Res 20 + 1 match 10 = 60
    assert res[0].score == 60.0

