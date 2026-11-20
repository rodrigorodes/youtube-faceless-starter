"""Estrutura do workflow 03 e comportamento dos nós Code (executados no Node, se existir)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WF = json.loads((ROOT / "workflows" / "03-publish-approved.json").read_text(encoding="utf-8"))
NODES = {n["name"]: n for n in WF["nodes"]}


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


def test_no_secrets_and_only_known_hosts():
    text = json.dumps(WF)
    assert not re.search(r"(?i)(client_secret|refresh_token|access_token|bearer\s+[a-z0-9._-]{10,}|AIza[0-9A-Za-z_-]{20,}|ya29\.)", text)
    for url in re.findall(r"https?://[^\s'\"+}]+", text):
        assert url.startswith(("http://renderer:8000", "https://www.googleapis.com/upload/youtube/v3/")), url


def test_workflow_ships_inactive_with_a_private_youtube_body_coming_from_the_renderer():
    assert WF["active"] is False
    assert "youtube_body" not in json.dumps(NODES["New session"]["parameters"])  # o corpo vem do contexto, montado pelo renderer
    assert NODES["New session"]["parameters"]["jsonBody"] == "={{ JSON.stringify($json.body) }}"
    assert "privacyStatus" not in json.dumps(WF)  # a privacidade é decidida no renderer (sempre private), não no workflow


def test_only_youtube_nodes_use_the_oauth_credential_and_never_follow_redirects_on_the_session():
    with_cred = {n for n, v in NODES.items() if "credentials" in v}
    assert with_cred == {"Check session", "New session", "Upload", "Set thumbnail"}
    for name in ("Check session", "Upload"):  # 308 = "incompleto", não redirecionamento
        assert NODES[name]["parameters"]["options"]["redirect"]["redirect"]["followRedirects"] is False


def test_recording_the_id_is_retried_and_thumbnail_failure_is_not_fatal():
    assert NODES["Mark uploaded"]["retryOnFail"] is True and NODES["Mark uploaded"]["maxTries"] >= 3
    assert NODES["Set thumbnail"]["onError"] == "continueRegularOutput" and NODES["Set thumbnail"]["maxTries"] == 3
    assert NODES["Report failure"]["onError"] == "continueRegularOutput"


node = shutil.which("node")
pytestmark_node = pytest.mark.skipif(node is None, reason="node not installed")

HARNESS = r"""
const [, name, ctxJson, inputJson, file] = process.argv;
const nodes = JSON.parse(require('fs').readFileSync(file, 'utf8')).nodes;
const code = nodes.find((n) => n.name === name).parameters.jsCode;
const ctx = JSON.parse(ctxJson), input = JSON.parse(inputJson);
const ref = (n) => ({ first: () => ({ json: n === 'Config' ? { debug_wait_after: '' } : ctx }) });
const fn = new Function('$input', '$', code);
console.log(JSON.stringify(fn({ first: () => ({ json: input }) }, ref)));
"""
CTX = {"pid": "p" * 32, "attempt": 2, "upload_uri": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=a", "size": 5000, "offset": 0}


def run(name, input_, ctx=CTX):
    out = subprocess.run([node, "-e", HARNESS, name, json.dumps(ctx), json.dumps(input_), str(ROOT / "workflows" / "03-publish-approved.json")],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)[0]["json"]


@pytestmark_node
@pytest.mark.parametrize("response,state,extra", [
    ({"statusCode": 200, "body": {"id": "oNQ2KN37sfQ"}}, "done", {"youtube_id": "oNQ2KN37sfQ"}),
    ({"statusCode": 201, "body": {"id": "oNQ2KN37sfQ"}}, "done", {"youtube_id": "oNQ2KN37sfQ"}),
    ({"statusCode": 308, "headers": {"range": "bytes=0-1999"}}, "partial", {"offset": 2000}),
    ({"statusCode": 308, "headers": {}}, "partial", {"offset": 0}),
    ({"statusCode": 404, "body": ""}, "expired", {"upload_uri": ""}),
    ({"statusCode": 410, "body": ""}, "expired", {}),
    ({"statusCode": 503, "body": "x"}, "retry", {"retryable": True}),
    ({"statusCode": 429, "body": "x"}, "retry", {"retryable": True}),
    ({"error": {"message": "socket hang up"}}, "retry", {"retryable": True}),
    ({"statusCode": 403, "body": {"error": {"message": "quotaExceeded"}}}, "fatal", {"retryable": False}),
    ({"statusCode": 401, "body": "unauthorized"}, "fatal", {"retryable": False}),
    ({"statusCode": 200, "body": {"kind": "outra coisa"}}, "fatal", {"retryable": False}),
    ({"statusCode": 200, "body": {"id": "curto"}}, "fatal", {}),
])
def test_session_state_classification(response, state, extra):
    out = run("Session state", response)
    assert out["state"] == state and all(out[k] == v for k, v in extra.items())
    assert out["pid"] == CTX["pid"] and out["attempt"] == 2  # o contexto segue adiante


@pytestmark_node
def test_partial_offset_never_reaches_the_file_size():
    assert run("Session state", {"statusCode": 308, "headers": {"range": "bytes=0-4999"}})["offset"] == 0  # tudo enviado mas sem confirmação: reenvia


@pytestmark_node
@pytest.mark.parametrize("response,state", [
    ({"statusCode": 200, "headers": {"location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=x"}}, "ok"),
    ({"statusCode": 200, "headers": {}}, "fatal"),
    ({"statusCode": 400, "body": "bad"}, "fatal"), ({"statusCode": 403, "body": "forbidden"}, "fatal"),
    ({"statusCode": 500, "body": "x"}, "retry"), ({"error": {"message": "timeout"}}, "retry"), ({"statusCode": 404, "body": ""}, "fatal"),
])
def test_session_created_classification(response, state):
    out = run("Session created", response)
    assert out["state"] == state
    if state == "ok":
        assert out["upload_uri"].startswith("https://www.googleapis.com/upload/") and out["offset"] == 0
    else:
        assert out["upload_uri"] == "" and "error" in out


@pytestmark_node
@pytest.mark.parametrize("response,state,retryable", [
    ({"statusCode": 200, "body": {"id": "oNQ2KN37sfQ"}}, "ok", None), ({"statusCode": 201, "body": {"id": "oNQ2KN37sfQ"}}, "ok", None),
    ({"statusCode": 500, "body": "x"}, "retry", True), ({"statusCode": 308, "headers": {}}, "retry", True), ({"error": {"message": "ECONNRESET"}}, "retry", True),
    ({"statusCode": 400, "body": {"error": "invalid"}}, "fatal", False), ({"statusCode": 403, "body": "quota"}, "fatal", False),
    ({"statusCode": 200, "body": ""}, "fatal", False),
])
def test_upload_result_classification(response, state, retryable):
    out = run("Upload result", response)
    assert out["state"] == state and (retryable is None or out["retryable"] is retryable)
    if state == "ok":
        assert out["youtube_id"] == "oNQ2KN37sfQ"
    else:
        assert len(out["error"]) <= 300


@pytestmark_node
def test_config_clamps_the_lease_and_only_allows_known_debug_points():
    def cfg(body):
        out = subprocess.run([node, "-e", "const code = JSON.parse(require('fs').readFileSync(process.argv[1],'utf8')).nodes.find(n=>n.name==='Config').parameters.jsCode;"
                              "console.log(JSON.stringify(new Function('$input', code)({first: () => ({json: JSON.parse(process.argv[2])})})))",
                              str(ROOT / "workflows" / "03-publish-approved.json"), json.dumps(body)], capture_output=True, text=True, check=True).stdout
        return json.loads(out)[0]["json"]
    assert cfg({}) == {"lease_seconds": 1800, "debug_wait_after": ""}
    assert cfg({"body": {"lease_seconds": 30, "debug_wait_after": "upload"}}) == {"lease_seconds": 30, "debug_wait_after": "upload"}
    assert cfg({"body": {"lease_seconds": 5, "debug_wait_after": "rm -rf"}}) == {"lease_seconds": 1800, "debug_wait_after": ""}
    assert cfg({"body": {"lease_seconds": 99999}})["lease_seconds"] == 1800
