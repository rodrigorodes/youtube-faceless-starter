import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import doctor  # noqa: E402

REQUIRED = ["POSTGRES_PASSWORD", "N8N_ENCRYPTION_KEY"]
SECRET = "s3cr3t-value-123"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def http_server():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == "/ok" else 500)
            self.end_headers()
            self.wfile.write(SECRET.encode())  # corpo nunca deve vazar para a saída

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def test_missing_and_blank_secret_fail_without_leaking_value():
    checks = doctor.check_env(f"POSTGRES_PASSWORD={SECRET}\nN8N_ENCRYPTION_KEY=\n", REQUIRED + ["OPENCODE_BRIDGE_TOKEN"])
    by = {c.name: c for c in checks}
    assert by["POSTGRES_PASSWORD"].ok
    assert not by["N8N_ENCRYPTION_KEY"].ok and not by["OPENCODE_BRIDGE_TOKEN"].ok
    assert all(SECRET not in c.detail for c in checks)


def test_env_parser_handles_comments_and_quotes():
    checks = doctor.check_env('# comentário\nPOSTGRES_PASSWORD="abc"\nN8N_ENCRYPTION_KEY=\'def\'\n', REQUIRED)
    assert all(c.ok for c in checks)


def test_optional_missing_is_not_required():
    c = doctor.check_env("", [], optional=["OPENCODE_BRIDGE_TOKEN"])[0]
    assert not c.ok and not c.required


def test_check_port(http_server):
    assert doctor.check_port("127.0.0.1", http_server, expect_open=True).ok
    assert not doctor.check_port("127.0.0.1", free_port(), expect_open=True).ok
    assert doctor.check_port("127.0.0.1", free_port(), expect_open=False).ok


def test_check_http_ok_error_and_refused(http_server):
    assert doctor.check_http(f"http://127.0.0.1:{http_server}/ok").ok
    bad = doctor.check_http(f"http://127.0.0.1:{http_server}/boom")
    assert not bad.ok and SECRET not in bad.detail
    assert not doctor.check_http(f"http://127.0.0.1:{free_port()}/x").ok


def test_main_returns_nonzero_when_env_missing(tmp_path):
    assert doctor.main(root=tmp_path, network=False) == 1


def test_main_zero_when_required_present_and_never_prints_secret(tmp_path, capsys):
    (tmp_path / ".env").write_text(f"POSTGRES_PASSWORD={SECRET}\nN8N_ENCRYPTION_KEY={SECRET}x\n")
    (tmp_path / ".env").chmod(0o600)
    assert doctor.main(root=tmp_path, network=False) == 0
    assert SECRET not in capsys.readouterr().out


def test_bridge_token_required_only_with_opencode_provider(tmp_path):
    (tmp_path / ".env").write_text(f"POSTGRES_PASSWORD=a\nN8N_ENCRYPTION_KEY=b\nAI_PROVIDER=opencode\n")
    assert doctor.main(root=tmp_path, network=False) == 1
