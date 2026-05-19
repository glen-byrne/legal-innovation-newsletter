"""Future publisher adapter boundary.

The MVP intentionally does not publish, send email, or create beehiiv drafts.
This interface keeps later beehiiv work separate from collection, ranking,
summarisation, rendering, QA, and archive review.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from legal_innovator.models import Issue


class Publisher(ABC):
    @abstractmethod
    def create_draft(self, issue: Issue, html: str, markdown: str, plaintext: str) -> str:
        """Create a draft and return a provider draft ID."""


class BeehiivPublisher(Publisher):
    def create_draft(self, issue: Issue, html: str, markdown: str, plaintext: str) -> str:
        raise NotImplementedError(
            "Beehiiv publishing is intentionally not implemented in the MVP. "
            "Add this after PR approval/merge workflow is defined."
        )
