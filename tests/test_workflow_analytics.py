import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "workflows" / "04-analytics-daily.json"
NODE = shutil.which("node")


def workflow():
    return json.loads(FILE.read_text())


def test_workflow_is_inactive_and_uses_separate_readonly_credential():
    wf = workflow()
    assert wf["active"] is False
    nodes = {node["name"]: node for node in wf["nodes"]}
    assert nodes["Read analytics"]["credentials"]["oAuth2Api"]["name"] == "youtube_analytics_readonly"
    assert nodes["Read analytics"]["parameters"]["authentication"] == "genericCredentialType"
    assert "youtube_videos_app" not in json.dumps(wf)
    assert nodes["Store metrics"]["parameters"]["url"] == "http://renderer:8000/studio/analytics/metrics"
    assert nodes["Store metrics"]["parameters"]["genericAuthType"] == "httpHeaderAuth"
    assert nodes["Store metrics"]["credentials"]["httpHeaderAuth"]["name"] == "studio_worker"
    assert nodes["Store metrics"]["parameters"]["options"]["redirect"]["redirect"]["followRedirects"] is False
    assert "https://youtubeanalytics.googleapis.com/v2/reports" in nodes["Read analytics"]["parameters"]["url"]


def run_code(name, reports, queries):
    code = next(n["parameters"]["jsCode"] for n in workflow()["nodes"] if n["name"] == name)
    script = """const [code, reports, queries] = process.argv.slice(1).map(JSON.parse);
const fn = new Function('$input', '$', code);
console.log(JSON.stringify(fn({all: () => reports.map(json => ({json}))},
  () => ({all: () => queries.map(json => ({json}))}))));"""
    out = subprocess.run([NODE, "-e", script, json.dumps(code), json.dumps(reports), json.dumps(queries)],
                         text=True, capture_output=True, check=True)
    return json.loads(out.stdout)


@pytest.mark.skipif(not NODE, reason="node missing")
def test_report_maps_named_columns_and_never_fabricates_missing_dates():
    vid = "a" * 32
    queries = [{"video_id": vid, "youtube_id": "oNQ2KN37sfQ", "start": "2026-11-01", "end": "2026-11-14"}]
    reports = [{"columnHeaders": [{"name": "views"}, {"name": "day"}, {"name": "likes"}],
                "rows": [[7, "2026-11-03", 2]]}]
    rows = run_code("Normalize reports", reports, queries)
    assert rows == [{"json": {"video_id": vid, "date": "2026-11-03", "views": 7, "likes": 2}}]
    assert run_code("Normalize reports", [{"columnHeaders": reports[0]["columnHeaders"], "rows": []}], queries) == []


@pytest.mark.skipif(not NODE, reason="node missing")
def test_report_rejects_malformed_and_out_of_window_rows():
    queries = [{"video_id": "a" * 32, "youtube_id": "oNQ2KN37sfQ", "start": "2026-11-01", "end": "2026-11-14"}]
    reports = [{"columnHeaders": [{"name": "day"}, {"name": "views"}], "rows": [["2026-10-31", 9]]}]
    with pytest.raises(subprocess.CalledProcessError):
        run_code("Normalize reports", reports, queries)
