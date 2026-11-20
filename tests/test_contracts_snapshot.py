import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_contracts  # noqa: E402


def test_committed_contracts_match_code():
    for rel, content in export_contracts.render_all().items():
        assert (ROOT / rel).read_text(encoding="utf-8") == content, f"{rel} desatualizado: rode scripts/export_contracts.py"


def test_every_entity_has_a_schema_and_diagram_lists_states():
    files = export_contracts.render_all()
    for name in ("project", "video", "script", "scene", "asset", "renderjob", "publication", "usageentry", "qareport", "sourcesnapshot", "claim", "factcheckreport", "approval", "renderplan"):
        assert f"contracts/v1/{name}.schema.json" in files
    assert "stateDiagram-v2" in files["docs/10-arquitetura.md"]


def test_check_mode_detects_drift(tmp_path):
    assert export_contracts.main(check=True, root=tmp_path) == 1
