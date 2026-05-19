"""Pipeline error types and lightweight stage reporting."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorStage(StrEnum):
    SOURCE_ACCESS = "source_access"
    ROBOTS = "robots"
    EXTRACTION = "extraction"
    OPENAI = "openai"
    CLASSIFICATION = "classification"
    DEDUPLICATION = "deduplication"
    RANKING = "ranking"
    SUMMARISATION = "summarisation"
    RENDERING = "rendering"
    ARCHIVE = "archive"
    PR = "pr"


@dataclass(slots=True)
class StageError:
    stage: ErrorStage
    message: str
    source: str | None = None
    url: str | None = None

    def as_markdown(self) -> str:
        parts = [f"**{self.stage.value}**", self.message]
        if self.source:
            parts.append(f"source: {self.source}")
        if self.url:
            parts.append(f"url: {self.url}")
        return " - ".join(parts)


class PipelineError(RuntimeError):
    """A recoverable pipeline failure with stage context."""

    def __init__(
        self,
        stage: ErrorStage,
        message: str,
        *,
        source: str | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage_error = StageError(stage=stage, message=message, source=source, url=url)
