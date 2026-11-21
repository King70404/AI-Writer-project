"""Settle-once usage rows and bounded aggregate reads.

A row is inserted as ``running`` right before a request goes out and is settled once
with its outcome. SQLite triggers reject a second settlement, identity changes and
deletion. No prompt, response, header, endpoint or key is stored.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    case,
    func,
    select,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from aiwebnovel.db.base import Base
from aiwebnovel.db.types import PrefixedUlidType
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.novel_structure.identifiers import ChapterId
from aiwebnovel.novel_structure.persistence.models import ChapterRecord
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.usage.budget import (
    AttemptCost,
    BudgetRefused,
    cache_cost_is_upper,
    format_amount,
    settled_cost,
)
from aiwebnovel.usage.models import (
    ModelUsage,
    OperationUsage,
    UsageAttemptView,
    UsageLedgerUnavailable,
    UsagePage,
    UsageTotals,
)
from aiwebnovel.usage.records import AttemptOutcome, AttemptStart

if TYPE_CHECKING:
    from aiwebnovel.usage.budget_persistence import SqlAlchemyBudgetStore


class ModelUsageAttemptRecord(Base):
    __tablename__ = "model_usage_attempts"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('generation','reference_analysis','story_review','connection_check',"
            "'method_trial','plan_proposal','foreshadow_extraction')",
            name="ck_model_usage_operation",
        ),
        CheckConstraint("model_kind IN ('local','cloud')", name="ck_model_usage_kind"),
        CheckConstraint(
            "status IN ('running','completed','failed','timeout','interrupted')",
            name="ck_model_usage_status",
        ),
        CheckConstraint(
            "usage_source IN ('provider_reported','unknown')", name="ck_model_usage_source"
        ),
        CheckConstraint(
            "input_characters >= 0 AND (output_characters IS NULL OR output_characters >= 0)"
            " AND (reported_input_tokens IS NULL OR reported_input_tokens >= 0)"
            " AND (reported_output_tokens IS NULL OR reported_output_tokens >= 0)"
            " AND (reported_total_tokens IS NULL OR reported_total_tokens >= 0)"
            " AND (duration_ms IS NULL OR duration_ms >= 0)",
            name="ck_model_usage_counts",
        ),
        CheckConstraint(
            "(usage_source = 'unknown' AND reported_input_tokens IS NULL"
            " AND reported_output_tokens IS NULL AND reported_total_tokens IS NULL)"
            " OR (usage_source = 'provider_reported' AND status = 'completed' AND"
            " (reported_input_tokens IS NOT NULL OR reported_output_tokens IS NOT NULL"
            " OR reported_total_tokens IS NOT NULL))",
            name="ck_model_usage_reported",
        ),
        CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND duration_ms IS NULL"
            " AND output_characters IS NULL AND error_code IS NULL)"
            " OR (status <> 'running' AND finished_at IS NOT NULL)",
            name="ck_model_usage_lifecycle",
        ),
        Index("ix_model_usage_project", "project_id", "started_at", "id"),
        Index("ix_model_usage_chapter", "chapter_id", "started_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    chapter_id: Mapped[ChapterId | None] = mapped_column(
        PrefixedUlidType(ChapterId), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=True
    )
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    input_characters: Mapped[int] = mapped_column(Integer, nullable=False)
    output_characters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    usage_source: Mapped[str] = mapped_column(String(20), nullable=False)
    reported_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reported_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reported_total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_details_status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


def _iso(value: datetime) -> str:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


_R = ModelUsageAttemptRecord


def _sum(expression: Any) -> Any:
    return func.coalesce(func.sum(expression), 0)


def _count(condition: Any) -> Any:
    return _sum(case((condition, 1), else_=0))


_REPORTED = _R.usage_source == "provider_reported"
_TOTAL_COLUMNS = (
    func.count(_R.id),
    _count(_R.status == "completed"),
    _count(_R.status == "failed"),
    _count(_R.status == "timeout"),
    _count(_R.status == "interrupted"),
    _count(_R.status == "running"),
    _count(_REPORTED),
    _count(_REPORTED & (_R.reported_input_tokens.is_(None) | _R.reported_output_tokens.is_(None))),
    _count(_R.usage_source == "unknown"),
    _sum(_R.reported_input_tokens),
    _sum(_R.reported_output_tokens),
    _sum(_R.reported_total_tokens),
    _sum(_R.input_characters),
    _sum(func.coalesce(_R.output_characters, 0)),
)


def _totals(row: Sequence[Any]) -> UsageTotals:
    values = [int(value) for value in row]
    return UsageTotals(
        attempts=values[0],
        completed=values[1],
        failed=values[2],
        timeout=values[3],
        interrupted=values[4],
        running=values[5],
        reported_attempts=values[6],
        incomplete_reports=values[7],
        unknown_attempts=values[8],
        reported_input_tokens=values[9],
        reported_output_tokens=values[10],
        reported_total_tokens=values[11],
        input_characters=values[12],
        output_characters=values[13],
    )


def _view(record: ModelUsageAttemptRecord) -> UsageAttemptView:
    return UsageAttemptView.model_validate(
        {
            "id": record.id,
            "chapter_id": None if record.chapter_id is None else str(record.chapter_id),
            "operation": record.operation,
            "task_id": record.task_id,
            "profile_id": record.profile_id,
            "model_kind": record.model_kind,
            "model_name": record.model_name,
            "status": record.status,
            "error_code": record.error_code,
            "usage_source": record.usage_source,
            "reported_input_tokens": record.reported_input_tokens,
            "reported_output_tokens": record.reported_output_tokens,
            "reported_total_tokens": record.reported_total_tokens,
            "input_characters": record.input_characters,
            "output_characters": record.output_characters,
            "started_at": _iso(record.started_at),
            "finished_at": None if record.finished_at is None else _iso(record.finished_at),
            "duration_ms": record.duration_ms,
            "cached_input_tokens": record.cached_input_tokens,
            "cache_write_tokens": record.cache_write_tokens,
            "cache_details_status": record.cache_details_status,
        }
    )


class SqlAlchemyUsageLedger:
    def __init__(
        self,
        sessions: Callable[[], Session],
        projects: ProjectQueryService,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        budgets: SqlAlchemyBudgetStore | None = None,
    ) -> None:
        self._sessions = sessions
        self._projects = projects
        self._clock = clock
        self._budgets = budgets

    def start(self, attempt: AttemptStart) -> str:
        """Open a running row; with a budget store, check and reserve in one transaction."""
        attribution = attempt.attribution
        try:
            with self._sessions() as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    project_id = (
                        None
                        if attribution.project_id is None
                        else ProjectId.parse(attribution.project_id)
                    )
                    chapter_id = None
                    if attribution.chapter_id is not None:
                        chapter_id = ChapterId.parse(attribution.chapter_id)
                        owner = session.scalar(
                            select(ChapterRecord.project_id).where(ChapterRecord.id == chapter_id)
                        )
                        if owner is None or (project_id is not None and owner != project_id):
                            raise UsageLedgerUnavailable
                        project_id = owner
                    if project_id is None:
                        raise UsageLedgerUnavailable
                    check = None
                    if self._budgets is not None and attempt.request is not None:
                        check = self._budgets.check(session, project_id, attempt.request)
                        if check.decision == "refused":
                            # Refused locally: nothing is sent and no ledger row is written.
                            raise BudgetRefused
                    identifier = str(uuid4())
                    session.add(
                        ModelUsageAttemptRecord(
                            id=identifier,
                            project_id=project_id,
                            chapter_id=chapter_id,
                            operation=attribution.operation,
                            task_id=attribution.task_id[:36],
                            profile_id=attempt.profile_id[:100],
                            model_kind=attempt.model_kind,
                            model_name=attempt.model_name[:200],
                            input_characters=attempt.input_characters,
                            output_characters=None,
                            status="running",
                            error_code=None,
                            usage_source="unknown",
                            reported_input_tokens=None,
                            reported_output_tokens=None,
                            reported_total_tokens=None,
                            cache_details_status="not_reported",
                            started_at=self._clock(),
                            finished_at=None,
                            duration_ms=None,
                        )
                    )
                    if self._budgets is not None and attempt.request is not None and check:
                        session.flush()
                        self._budgets.reserve(
                            session,
                            identifier,
                            project_id,
                            attempt.request,
                            check.price,
                            check.estimated_micros,
                        )
                    session.commit()
                    return identifier
                except BaseException:
                    session.rollback()
                    raise
        except (UsageLedgerUnavailable, BudgetRefused):
            raise
        except (SQLAlchemyError, ValueError, DomainError):
            raise UsageLedgerUnavailable from None

    def settle(self, attempt_id: str, outcome: AttemptOutcome) -> bool:
        """Settle a running row once; returns ``False`` if it was already settled."""
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            record = session.get(ModelUsageAttemptRecord, attempt_id)
            if record is None or record.status != "running":
                session.rollback()
                return False
            finished = self._clock()
            usage = outcome.usage if outcome.status == "completed" else None
            record.status = outcome.status
            record.error_code = None if outcome.error_code is None else outcome.error_code[:80]
            record.output_characters = outcome.output_characters
            record.usage_source = "unknown" if usage is None else "provider_reported"
            record.reported_input_tokens = None if usage is None else usage.input_tokens
            record.reported_output_tokens = None if usage is None else usage.output_tokens
            record.reported_total_tokens = None if usage is None else usage.total_tokens
            record.cached_input_tokens = None if usage is None else usage.cached_input_tokens
            record.cache_write_tokens = None if usage is None else usage.cache_write_tokens
            record.cache_details_status = (
                "not_reported" if usage is None else usage.cache_details_status
            )
            record.finished_at = finished
            record.duration_ms = max(
                0, int((_aware(finished) - _aware(record.started_at)).total_seconds() * 1000)
            )
            session.commit()
            return True

    def recover_interrupted(self) -> int:
        """Mark rows left running by a previous process; call only at exclusive startup."""
        with self._sessions() as session:
            result = session.execute(
                update(ModelUsageAttemptRecord)
                .where(ModelUsageAttemptRecord.status == "running")
                .values(status="interrupted", finished_at=self._clock())
            )
            session.commit()
            return int(cast(Any, result).rowcount or 0)

    def page(
        self,
        project_id: str,
        chapter_id: str | None,
        task_id: str | None,
        offset: int,
        limit: int,
    ) -> UsagePage:
        identifier = ProjectId.parse(project_id)
        chapter = None if chapter_id is None else ChapterId.parse(chapter_id)
        # The project query service hides logically deleted Projects.
        if self._projects.get_project(GetProjectQuery(project_id)) is None:
            raise ProjectNotFound(identifier)
        conditions: list[Any] = [_R.project_id == identifier]
        if chapter is not None:
            conditions.append(_R.chapter_id == chapter)
        if task_id is not None:
            conditions.append(_R.task_id == task_id)
        with self._sessions() as session:
            totals = _totals(session.execute(select(*_TOTAL_COLUMNS).where(*conditions)).one())
            operations = [
                OperationUsage.model_validate({"operation": row[0], "totals": _totals(row[1:])})
                for row in session.execute(
                    select(_R.operation, *_TOTAL_COLUMNS)
                    .where(*conditions)
                    .group_by(_R.operation)
                    .order_by(_R.operation)
                )
            ]
            models = [
                ModelUsage.model_validate(
                    {"model_kind": row[0], "model_name": row[1], "totals": _totals(row[2:])}
                )
                for row in session.execute(
                    select(_R.model_kind, _R.model_name, *_TOTAL_COLUMNS)
                    .where(*conditions)
                    .group_by(_R.model_kind, _R.model_name)
                    .order_by(_R.model_kind, _R.model_name)
                )
            ]
            from aiwebnovel.usage.budget_persistence import (
                ModelBudgetReservationRecord as Reservation,
            )
            from aiwebnovel.usage.budget_persistence import (
                ModelPriceRevisionRecord as PriceRecord,
            )

            records = session.execute(
                select(_R, Reservation, PriceRecord)
                .outerjoin(Reservation, Reservation.attempt_id == _R.id)
                .outerjoin(PriceRecord, PriceRecord.id == Reservation.price_revision_id)
                .where(*conditions)
                .order_by(_R.started_at.desc(), _R.id.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            items = []
            for record, reservation, price in records:
                view = _view(record)
                if reservation is not None and price is not None:
                    cost_row = AttemptCost(
                        record.status,
                        record.reported_input_tokens,
                        record.reported_output_tokens,
                        record.reported_total_tokens,
                        reservation.reserved_micros,
                        reservation.currency,
                        price.input_micros_per_million,
                        price.output_micros_per_million,
                        record.cached_input_tokens,
                        record.cache_write_tokens,
                        price.cached_input_micros_per_million,
                        price.cache_write_micros_per_million,
                        record.cache_details_status,
                    )
                    cost = settled_cost(cost_row)
                    basis = (
                        "reserved_upper"
                        if cost is None
                        else (
                            ("cache_upper" if cache_cost_is_upper(cost_row) else "reported_tokens")
                            if record.reported_input_tokens is not None
                            and record.reported_output_tokens is not None
                            else "total_tokens_upper"
                        )
                    )
                    values = view.model_dump()
                    values.update(
                        price_version=price.version,
                        input_per_million=format_amount(price.input_micros_per_million),
                        output_per_million=format_amount(price.output_micros_per_million),
                        cached_input_per_million=None
                        if price.cached_input_micros_per_million is None
                        else format_amount(price.cached_input_micros_per_million),
                        cache_write_per_million=None
                        if price.cache_write_micros_per_million is None
                        else format_amount(price.cache_write_micros_per_million),
                        currency=reservation.currency,
                        amount=format_amount(reservation.reserved_micros if cost is None else cost),
                        amount_basis=basis,
                    )
                    view = UsageAttemptView.model_validate(values)
                items.append(view)
        following = offset + len(items)
        return UsagePage(
            project_id=str(identifier),
            chapter_id=None if chapter is None else str(chapter),
            task_id=task_id,
            totals=totals,
            by_operation=operations,
            by_model=models,
            items=items,
            total=totals.attempts,
            next_offset=following if following < totals.attempts else None,
        )
