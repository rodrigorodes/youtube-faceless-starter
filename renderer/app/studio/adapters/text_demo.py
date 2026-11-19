"""TextModel de demonstração: monta o roteiro com as próprias claims do prompt, sem LLM (testes e2e offline)."""
import json
import re

from ..application.ports import TextResult
from ..domain.contracts import UsageEntry

_CLAIM = re.compile(r"^\[([0-9a-f]{10})\] (.+)$", re.M)
_COUNT = re.compile(r"com (\d+) cenas")


class DemoText:
    name = "demo"

    def __init__(self, model: str):
        self.model = model

    def cost_estimate(self, prompt: str) -> float:
        return 0.0

    def complete(self, prompt: str, *, json_schema: dict | None = None) -> TextResult:
        claims = _CLAIM.findall(prompt)
        count = int(m.group(1)) if (m := _COUNT.search(prompt)) else 4
        scenes = [{"narration": claims[i % len(claims)][1], "caption": "", "label": f"FATO {i + 1}",
                   "image_prompt": "abstract colorful light trails on a dark stage background, no people",
                   "claim_ids": [claims[i % len(claims)][0]]} for i in range(count)] if claims else []
        return TextResult(text=json.dumps({"scenes": scenes}, ensure_ascii=False),
                          usage=UsageEntry(step="text", provider=self.name, model=self.model, cost_usd=0.0))
