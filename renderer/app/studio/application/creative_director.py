"""Caso de uso do Diretor Criativo: gera o CreativeBrief estruturado para um tema e canal."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from ..domain.creative_director import CreativeBrief
from .budget import PaidOperationGuard, paid_key, provider_settlement
from .ports import TextModel

if TYPE_CHECKING:
    from .ports import TextResult


class CreateCreativeBrief:
    """Gera um briefing criativo de alto nível utilizando um modelo de texto."""

    def __init__(self, text_model: TextModel, guard: PaidOperationGuard | None = None) -> None:
        self.text_model = text_model
        self.guard = guard

    def _build_prompt(self, topic: str, channel_context: dict[str, Any], budget_cap: float | None = None) -> str:
        context_items: list[str] = []
        for k, v in sorted(channel_context.items(), key=lambda x: str(x[0])):
            if v is not None:
                context_items.append(f"- {k}: {v}")
        ctx_str = "\n".join(context_items) if context_items else "Nenhum contexto específico informado."
        budget_str = f"- Teto de orçamento: ${budget_cap:.2f} USD\n" if budget_cap is not None else ""

        return (
            "Você é um Diretor Criativo audiovisual especializado em roteirização e produção para canais do YouTube.\n"
            "Sua missão é gerar um briefing criativo estruturado (CreativeBrief) que guiará o roteiro e a seleção visual.\n\n"
            f"TEMA:\n{topic}\n\n"
            f"CONTEXTO DO CANAL:\n{ctx_str}\n\n"
            + budget_str +
            "\nResponda ESTRITAMENTE com um objeto JSON válido (sem comentários ou texto fora do JSON) "
            "conforme a estrutura do CreativeBrief:\n"
            "{\n"
            '  "schema_version": 1,\n'
            '  "topic": string (tema do vídeo),\n'
            '  "narrative_goal": string (objetivo narrativo),\n'
            '  "hook": string (gancho nos primeiros segundos),\n'
            '  "content_structure": [string, string, ...] (no mínimo 2 seções),\n'
            '  "tone": string (tom narrativo),\n'
            '  "pacing": string (ritmo narrativo e visual),\n'
            '  "visual_direction": string (diretrizes visuais para as cenas),\n'
            '  "recommended_media_types": ["image", "video"] (itens dentre "image", "video", "graphic", "text"),\n'
            '  "caption_strategy": string (estratégia de legendas),\n'
            '  "audio_guidance": string (orientações de áudio e música),\n'
            '  "max_budget_usd": number | null,\n'
            '  "quality_criteria": [string, ...]\n'
            "}"
        )

    def _parse(self, raw: str, budget_cap: float | None) -> CreativeBrief:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("model output is not valid JSON")
        json_str = raw[start:end + 1]
        brief = CreativeBrief.model_validate_json(json_str)
        if budget_cap is not None:
            if brief.max_budget_usd is not None and brief.max_budget_usd > budget_cap:
                brief = brief.model_copy(update={"max_budget_usd": float(budget_cap)})
            elif brief.max_budget_usd is None:
                brief = brief.model_copy(update={"max_budget_usd": float(budget_cap)})
        return brief

    def execute(self, topic: str, channel_context: dict[str, Any], budget_cap: float | None = None) -> CreativeBrief:
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("topic must not be blank")
        if not isinstance(channel_context, dict):
            raise ValueError("channel_context must be a dict")
        if budget_cap is not None and (not isinstance(budget_cap, (int, float)) or budget_cap < 0):
            raise ValueError("budget_cap must be non-negative")

        model = self.text_model
        prompt = self._build_prompt(topic, channel_context, budget_cap)
        schema = CreativeBrief.model_json_schema()

        if self.guard is None:
            result = model.complete(prompt, json_schema=schema)
            return self._parse(result.text, budget_cap)

        video_id = channel_context.get("video_id") if isinstance(channel_context, dict) else None
        key = paid_key("creative_direction", video_id or "", getattr(model, "model", ""), model.name, prompt)
        estimate = model.cost_estimate(prompt)

        return self.guard.run(
            key,
            video_id,
            Decimal(str(estimate)),
            call=lambda: model.complete(prompt, json_schema=schema),
            validate=lambda res: self._parse(res.text, budget_cap),
            settle=lambda res: provider_settlement(res.usage, settled_by=f"studio:creative_director:{model.name}"),
        )
