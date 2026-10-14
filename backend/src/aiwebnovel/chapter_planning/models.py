"""Bounded chapter planning contracts; list order is the author's scene/beat order."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from aiwebnovel.domain.errors import DomainError


class PlanningConflict(DomainError):
    message = "The chapter plan changed. Reload it before saving."


class PlanningReferenceInvalid(DomainError):
    message = "A selected story asset or writing rule is unavailable in this project."


Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_-]+$"),
]
Focus = Annotated[str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)]


class PlanningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PlannedBeat(PlanningModel):
    id: Identifier
    action: str = Field(max_length=1000)
    change: str = Field(max_length=1000)


class PlannedScene(PlanningModel):
    id: Identifier
    title: str = Field(max_length=120)
    setting: str = Field(max_length=500)
    character_ids: list[Identifier] = Field(max_length=20)
    beats: list[PlannedBeat] = Field(max_length=12)


class ChapterPlanDocument(PlanningModel):
    memory_focuses: list[Focus] = Field(min_length=1, max_length=3)
    target_characters: int = Field(ge=200, le=20_000)
    chapter_goal: str = Field(max_length=2000)
    conflict: str = Field(max_length=2000)
    continuity_notes: str = Field(max_length=4000)
    scenes: list[PlannedScene] = Field(max_length=12)
    include_story_bible: bool
    writing_rule_revision_ids: list[Identifier] = Field(max_length=8)

    @model_validator(mode="after")
    def consistent_document(self) -> Self:
        sequences = [
            self.memory_focuses,
            [scene.id for scene in self.scenes],
            self.writing_rule_revision_ids,
            *[scene.character_ids for scene in self.scenes],
            *[[beat.id for beat in scene.beats] for scene in self.scenes],
        ]
        if any(len(sequence) != len(set(sequence)) for sequence in sequences):
            raise ValueError("Planning identifiers and memory focuses must not repeat.")
        # Reject unpaired surrogates and controls that cannot safely cross the model boundary.
        for text in self._texts():
            if any((ord(c) < 32 and c not in "\n\r\t") or 0xD800 <= ord(c) <= 0xDFFF for c in text):
                raise ValueError("Planning text contains unsupported control characters.")
        serialized = self.model_dump_json(include=set(ChapterPlanDocument.model_fields))
        if len(serialized) > 12_000:
            raise ValueError("The chapter plan must fit within 12000 characters.")
        return self

    def _texts(self) -> list[str]:
        return [
            *self.memory_focuses,
            self.chapter_goal,
            self.conflict,
            self.continuity_notes,
            *self.writing_rule_revision_ids,
            *[value for s in self.scenes for value in (s.id, s.title, s.setting, *s.character_ids)],
            *[value for s in self.scenes for b in s.beats for value in (b.id, b.action, b.change)],
        ]


class SaveChapterPlan(ChapterPlanDocument):
    expected_version: int = Field(ge=0)


class ChapterPlan(ChapterPlanDocument):
    chapter_id: str
    project_id: str
    version: int = Field(ge=1)
    revision_id: str
    updated_at: str
