"""Gera contracts/v1/*.schema.json e docs/10-arquitetura.md a partir do código.

Uso: python scripts/export_contracts.py [--check]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderer"))

from app.studio.domain import contracts as c  # noqa: E402
from app.studio.domain.render_plan import RenderPlan  # noqa: E402
from app.studio.domain.states import to_mermaid  # noqa: E402

MODELS = [c.Project, c.Video, c.Script, c.Scene, c.Asset, c.RenderJob, c.Publication, c.UsageEntry, c.QaReport, c.SourceSnapshot, c.Claim, c.FactCheckReport, c.Approval, RenderPlan]


def render_all() -> dict[str, str]:
    files = {f"contracts/v{c.SCHEMA_VERSION}/{m.__name__.lower()}.schema.json":
             json.dumps(m.model_json_schema(), sort_keys=True, indent=2, ensure_ascii=False) + "\n" for m in MODELS}
    rows = "\n".join(f"| `{m.__name__}` | `contracts/v{c.SCHEMA_VERSION}/{m.__name__.lower()}.schema.json` |" for m in MODELS)
    files["docs/10-arquitetura.md"] = (
        "# Arquitetura e contratos (gerado)\n\n"
        "> Gerado por `scripts/export_contracts.py`. Não edite à mão.\n\n"
        "## Camadas\n\n`domain` ← `application` ← `adapters` / `api`. Só `composition.py` conhece adaptadores concretos.\n\n"
        f"## Estados do vídeo\n\n```mermaid\n{to_mermaid()}\n```\n\n## Entidades\n\n| Entidade | Schema |\n|---|---|\n{rows}\n")
    return files


def main(check: bool = False, root: Path = ROOT) -> int:
    drift = 0
    for rel, content in render_all().items():
        path = root / rel
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                print(f"desatualizado: {rel}")
                drift = 1
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return drift


if __name__ == "__main__":
    sys.exit(main(check="--check" in sys.argv))
