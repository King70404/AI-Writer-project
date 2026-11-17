"""Atomic trial transitions and isolated author method records."""

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.writing_studio.application.methods import (
    Annotation,
    Baseline,
    Candidate,
    MethodTemplate,
    Score,
    Trial,
    finish,
)
from aiwebnovel.writing_studio.application.models import (
    WritingConflict,
    WritingNotFound,
    WritingRule,
)
from aiwebnovel.writing_studio.persistence.method_models import (
    MethodAnnotationRecord,
    MethodTemplateRecord,
    MethodTrialRecord,
)


def _trial(payload: dict[str, Any]) -> Trial:
    data = dict(payload)
    baseline = dict(data["baseline"])
    rule = dict(baseline["rule"])
    rule["scene_tags"] = tuple(rule.get("scene_tags", ()))
    baseline["rule"] = WritingRule(**rule)
    data["baseline"] = Baseline(**baseline)
    data["without"] = Candidate(**data["without"])
    data["with_rule"] = Candidate(**data["with_rule"])
    for key in ("a_score", "b_score"):
        if data[key] is not None:
            data[key] = Score(**data[key])
    if data["model_snapshot"] is not None:
        data["model_snapshot"] = ModelSnapshot(**data["model_snapshot"])
    return Trial(**data)


class MethodRepository:
    def __init__(self, sessions: Callable[[], Session], projects: ProjectQueryService) -> None:
        self._sessions = sessions
        self._projects = projects

    def recover_interrupted(self) -> None:
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            for record in session.scalars(select(MethodTrialRecord)):
                if self._projects.get_project(GetProjectQuery(str(record.project_id))) is None:
                    continue
                trial = _trial(record.payload)
                changed = False
                if trial.without.status == "running":
                    trial = finish(trial, "without", text=None, error="AIProviderInterrupted")
                    changed = True
                if trial.with_rule.status == "running":
                    trial = finish(trial, "with", text=None, error="AIProviderInterrupted")
                    changed = True
                if changed:
                    record.payload = asdict(trial)
                    record.version += 1
            session.commit()

    def _active(self, project_id: str) -> ProjectId:
        identifier = ProjectId.parse(project_id)
        if self._projects.get_project(GetProjectQuery(project_id)) is None:
            raise WritingNotFound
        return identifier

    def create(self, trial: Trial) -> Trial:
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            project = self._active(trial.baseline.project_id)
            session.add(
                MethodTrialRecord(
                    id=trial.id,
                    project_id=project,
                    chapter_id=trial.baseline.chapter_id,
                    rule_version_id=trial.baseline.rule_version_id,
                    version=1,
                    payload=asdict(trial),
                )
            )
            session.commit()
        return trial

    def get(self, project_id: str, trial_id: str) -> tuple[Trial, int]:
        project = self._active(project_id)
        with self._sessions() as session:
            record = session.scalar(
                select(MethodTrialRecord).where(
                    MethodTrialRecord.id == trial_id, MethodTrialRecord.project_id == project
                )
            )
            if record is None:
                raise WritingNotFound
            return _trial(record.payload), record.version

    def list_trials(self, project_id: str, chapter_id: str) -> tuple[tuple[Trial, int], ...]:
        project = self._active(project_id)
        with self._sessions() as session:
            records = session.scalars(
                select(MethodTrialRecord)
                .where(
                    MethodTrialRecord.project_id == project,
                    MethodTrialRecord.chapter_id == chapter_id,
                )
                .order_by(MethodTrialRecord.id.desc())
                .limit(100)
            ).all()
            return tuple((_trial(record.payload), record.version) for record in records)

    def mutate(
        self,
        project_id: str,
        trial_id: str,
        expected_version: int,
        transition: Callable[[Trial], Trial],
    ) -> tuple[Trial, int]:
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            project = self._active(project_id)
            record = session.scalar(
                select(MethodTrialRecord).where(
                    MethodTrialRecord.id == trial_id, MethodTrialRecord.project_id == project
                )
            )
            if record is None:
                raise WritingNotFound
            if record.version != expected_version:
                raise WritingConflict
            trial = transition(_trial(record.payload))
            record.payload = asdict(trial)
            record.version += 1
            version = record.version
            session.commit()
            return trial, version

    def add_annotation(self, annotation_id: str, annotation: Annotation) -> None:
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            project = self._active(annotation.baseline.project_id)
            session.add(
                MethodAnnotationRecord(
                    id=annotation_id,
                    project_id=project,
                    chapter_id=annotation.baseline.chapter_id,
                    rule_version_id=annotation.baseline.rule_version_id,
                    payload={
                        "manuscript_revision_id": annotation.baseline.manuscript_revision_id,
                        "rule_index": annotation.rule_index,
                        "start": annotation.start,
                        "end": annotation.end,
                        "judgment": annotation.judgment,
                        "reason": annotation.reason,
                    },
                )
            )
            session.commit()

    def list_annotations(self, project_id: str, chapter_id: str) -> tuple[dict[str, Any], ...]:
        project = self._active(project_id)
        with self._sessions() as session:
            records = session.scalars(
                select(MethodAnnotationRecord)
                .where(
                    MethodAnnotationRecord.project_id == project,
                    MethodAnnotationRecord.chapter_id == chapter_id,
                )
                .order_by(MethodAnnotationRecord.id)
            ).all()
            return tuple(
                {
                    "id": record.id,
                    "chapter_id": record.chapter_id,
                    "rule_version_id": record.rule_version_id,
                    **record.payload,
                }
                for record in records
            )

    def add_template(self, template: MethodTemplate) -> None:
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            self._active(template.source_project_id)
            session.add(MethodTemplateRecord(id=template.id, payload=asdict(template)))
            session.commit()

    def has_validation(self, project_id: str, rule_version_id: str, rule_index: int) -> bool:
        project = self._active(project_id)
        with self._sessions() as session:
            annotations = session.scalars(
                select(MethodAnnotationRecord).where(
                    MethodAnnotationRecord.project_id == project,
                    MethodAnnotationRecord.rule_version_id == rule_version_id,
                )
            )
            if any(row.payload.get("rule_index") == rule_index for row in annotations):
                return True
            trials = session.scalars(
                select(MethodTrialRecord).where(
                    MethodTrialRecord.project_id == project,
                    MethodTrialRecord.rule_version_id == rule_version_id,
                )
            )
            return any(
                row.payload.get("baseline", {}).get("rule_index") == rule_index
                and row.payload.get("a_score") is not None
                for row in trials
            )

    def list_templates(self) -> tuple[MethodTemplate, ...]:
        with self._sessions() as session:
            records = session.scalars(
                select(MethodTemplateRecord).order_by(MethodTemplateRecord.id)
            ).all()
            return tuple(
                MethodTemplate(
                    **{**record.payload, "scene_tags": tuple(record.payload["scene_tags"])}
                )
                for record in records
            )

    def get_template(self, template_id: str) -> MethodTemplate:
        with self._sessions() as session:
            record = session.get(MethodTemplateRecord, template_id)
            if record is None:
                raise WritingNotFound
            return MethodTemplate(
                **{**record.payload, "scene_tags": tuple(record.payload["scene_tags"])}
            )

    def delete_template(self, template_id: str) -> None:
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            record = session.get(MethodTemplateRecord, template_id)
            if record is None:
                raise WritingNotFound
            session.delete(record)
            session.commit()
