"""OpenAI structured JSON helper."""

from __future__ import annotations

import json
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from legal_innovator.config import Settings
from legal_innovator.errors import ErrorStage, PipelineError

T = TypeVar("T", bound=BaseModel)


class StructuredAIClient:
    """Small adapter for OpenAI JSON-mode calls with one validation retry."""

    def __init__(self, settings: Settings) -> None:
        settings.validate_for_live_ai()
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

    def complete_json(
        self,
        *,
        schema: type[T],
        system: str,
        user: str,
        high_quality: bool = False,
    ) -> T:
        model = self.settings.openai_model_high_quality if high_quality else self.settings.openai_model_fast
        assert model
        errors: list[str] = []
        prompt = user
        for attempt in range(2):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                )
                content = response.choices[0].message.content or "{}"
                data = json.loads(content)
                return schema.model_validate(data)
            except (ValidationError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                errors.append(str(exc))
                prompt = (
                    f"{user}\n\nYour previous response failed validation. "
                    f"Return only valid JSON matching this schema: {schema.model_json_schema()}. "
                    f"Validation error: {exc}"
                )
            except Exception as exc:  # noqa: BLE001 - surface provider failures with stage context.
                raise PipelineError(ErrorStage.OPENAI, f"OpenAI API failure: {exc}") from exc
        raise PipelineError(ErrorStage.OPENAI, "OpenAI response failed JSON validation after retry: " + " | ".join(errors))
