import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "workflows" / "05-trends-daily.json"
NODE = shutil.which("node")


def workflow():
    return json.loads(FILE.read_text())


def test_trends_workflow_is_inactive_and_uses_safe_credentials():
    wf = workflow()
    assert wf["active"] is False
    nodes = {node["name"]: node for node in wf["nodes"]}
    assert nodes["Search YouTube"]["credentials"]["httpHeaderAuth"]["name"] == "youtube_data_readonly"
    assert nodes["Store Trends"]["credentials"]["httpHeaderAuth"]["name"] == "studio_worker"
    assert nodes["Store Trends"]["parameters"]["url"] == "http://renderer:8000/studio/trends"
    assert nodes["Store Trends"]["parameters"]["options"]["redirect"]["redirect"]["followRedirects"] is False
    assert "https://www.googleapis.com/youtube/v3/search" in nodes["Search YouTube"]["parameters"]["url"]


def run_format_trends(search_results, config):
    code = next(n["parameters"]["jsCode"] for n in workflow()["nodes"] if n["name"] == "Format Trends")
    script = """const [code, searchResults, config] = process.argv.slice(1).map(JSON.parse);
const fn = new Function('$input', '$', code);
console.log(JSON.stringify(fn({all: () => searchResults.map(json => ({json}))},
  () => ({first: () => ({json: config})}))));"""
    out = subprocess.run([NODE, "-e", script, json.dumps(code), json.dumps(search_results), json.dumps(config)],
                         text=True, capture_output=True, check=True)
    return json.loads(out.stdout)


@pytest.mark.skipif(not NODE, reason="node missing")
def test_format_trends_node_formats_valid_payload():
    pid = "a" * 32
    config = {"projectId": pid, "queries": ["ADE Lineup 2026"]}
    search_results = [{
        "query": "ADE Lineup 2026",
        "items": [
            {
                "id": {"videoId": "video123"},
                "snippet": {
                    "title": "ADE 2026 Lineup Anunciado",
                    "channelTitle": "ADE Official",
                    "publishedAt": "2026-11-18T10:00:00Z"
                }
            }
        ]
    }]

    res = run_format_trends(search_results, config)
    assert len(res) == 1
    batch = res[0]["json"]
    assert batch["project_id"] == pid
    assert len(batch["items"]) == 1
    item = batch["items"][0]
    assert item["topic"] == "ADE Lineup 2026"
    assert item["source_name"] == "YouTube Data API"
    assert len(item["evidence"]) == 1
    assert item["evidence"][0]["url"] == "https://youtube.com/watch?v=video123"


@pytest.mark.skipif(not NODE, reason="node missing")
def test_format_trends_returns_empty_when_no_items_or_no_project():
    config = {"projectId": "", "queries": []}
    res = run_format_trends([], config)
    assert res == []
