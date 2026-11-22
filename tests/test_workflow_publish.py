"""Contrato do workflow 03 (F01.T02): o Core executa a publicação; o n8n só orquestra.

O workflow não carrega credencial do YouTube nem faz PUT no `upload_uri`: ele chama
`POST /studio/publications/execute`, que roda claim + token do grant + gate de identidade +
upload + settle no Core. Resultado ambíguo nunca é tratado como sucesso.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("OUTPUT_DIR", "/tmp/yfs-test/output")
os.environ.setdefault("JOB_DIR", "/tmp/yfs-test/jobs")

ROOT = Path(__file__).resolve().parents[1]
WF = json.loads((ROOT / "workflows" / "03-publish-approved.json").read_text(encoding="utf-8"))
NODES = {n["name"]: n for n in WF["nodes"]}
node = shutil.which("node")


def test_every_connection_points_to_real_nodes_and_every_node_is_reachable():
    reachable, queue = set(), ["Every 2 minutes", "Run now (webhook)"]
    while queue:
        name = queue.pop()
        if name in reachable:
            continue
        reachable.add(name)
        for outputs in WF["connections"].get(name, {}).get("main", []):
            for edge in outputs:
                assert edge["node"] in NODES, f"{name} -> {edge['node']} não existe"
                queue.append(edge["node"])
    assert reachable == set(NODES), set(NODES) - reachable


def test_no_secrets_and_only_the_renderer_host():
    text = json.dumps(WF)
    assert not re.search(
        r"(?i)(client_secret|refresh_token|access_token|bearer\s+[a-z0-9._-]{10,}|AIza[0-9A-Za-z_-]{20,}|ya29\.)", text)
    for url in re.findall(r"https?://[^\s'\"+}]+", text):
        assert url.startswith("http://renderer:8000"), url


def test_workflow_ships_inactive():
    assert WF["active"] is False


def test_no_node_carries_a_youtube_credential():
    """O gate de identidade do Core não pode ser contornado por credencial própria no n8n."""
    for name, cfg in NODES.items():
        creds = cfg.get("credentials", {})
        assert "youTubeOAuth2Api" not in creds, name
        assert cfg.get("parameters", {}).get("nodeCredentialType") != "youTubeOAuth2Api", name
    assert "googleapis.com" not in json.dumps(WF)


def test_the_only_execution_path_is_the_core_endpoint():
    execute = NODES["Execute (Core)"]
    params = execute["parameters"]
    assert params["method"] == "POST"
    assert params["url"] == "http://renderer:8000/studio/publications/execute"
    assert params["authentication"] == "genericCredentialType"  # credencial do worker, não do YouTube


def test_config_ignores_untrusted_parameters_and_caps_attempts():
    if node is None:
        pytest.skip("node unavailable")
    script = ("const code = JSON.parse(require('fs').readFileSync(process.argv[1],'utf8'))"
              ".nodes.find(n=>n.name==='Config').parameters.jsCode;"
              "console.log(JSON.stringify(new Function('$input', code)"
              "({first: () => ({json: JSON.parse(process.argv[2])})})))")

    def cfg(body):
        out = subprocess.run([node, "-e", script, str(ROOT / "workflows" / "03-publish-approved.json"),
                              json.dumps(body)], capture_output=True, text=True, check=True).stdout
        return json.loads(out)[0]["json"]

    expected = {"lease_seconds": 5400, "max_attempts": 3}
    assert cfg({}) == expected
    assert cfg({"body": {"lease_seconds": 20, "max_attempts": 99}}) == expected


def test_result_switch_covers_every_outcome_and_defaults_to_blocked():
    """O switch tem que separar publicado, nada a fazer e reconciliação — e nunca cair em sucesso."""
    rules = NODES["Result"]["parameters"]["rules"]["values"]
    values = [rule["conditions"]["conditions"][0]["rightValue"] for rule in rules]
    assert values == ["UPLOADED", "IDLE", "RECONCILE"]
    # a saída de fallback é a de bloqueio/DLQ
    fallback = NODES["Result"]["parameters"]["options"]["fallbackOutput"]
    targets = WF["connections"]["Result"]["main"]
    blocked = targets[fallback][0]["node"]
    assert blocked == "Bloqueado ou DLQ"
    assert targets[0][0]["node"] == "Set thumbnail"
    assert targets[1][0]["node"] == "Nada a publicar"
    assert targets[2][0]["node"] == "Reconciliação necessária"


def test_thumbnail_is_non_fatal_and_uses_the_core():
    thumb = NODES["Set thumbnail"]["parameters"]
    assert thumb["url"].startswith("={{ 'http://renderer:8000/studio/publications/'")
    assert "/thumbnail-set" in thumb["url"]
    assert thumb["authentication"] == "genericCredentialType"
    code = NODES["Thumbnail outcome"]["parameters"]["jsCode"]
    assert "thumbnail_ok" in code


def test_execute_endpoint_requires_the_worker_credential():
    from fastapi.testclient import TestClient
    import sys

    sys.path.insert(0, str(ROOT / "renderer"))
    from app.main import app

    r = TestClient(app).post("/studio/publications/execute", json={"lease_seconds": 60})
    assert r.status_code == 401


def test_readme_documents_that_the_core_executes_the_upload():
    readme = (ROOT / "workflows" / "README-publish-approval.md").read_text(encoding="utf-8")
    assert "\"active\": false" in readme or "`\"active\": false`" in readme
    assert "/studio/publications/execute" in readme