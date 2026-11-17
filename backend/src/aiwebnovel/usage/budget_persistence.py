"""Append-only prices, budgets and send reservations; evaluation inside one transaction.

Every row is immutable (SQLite triggers reject update and delete). A strict budget
is checked and the reservation written in the same ``BEGIN IMMEDIATE`` transaction
that opens the usage ledger row, so two windows cannot overspend together.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, tzinfo
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from aiwebnovel.db.base import Base
from aiwebnovel.db.types import PrefixedUlidType
from aiwebnovel.novel_structure.identifiers import ChapterId
from aiwebnovel.novel_structure.persistence.models import ChapterRecord
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.usage.budget import (
    AttemptCost,
    Budget,
    BudgetCheck,
    BudgetInputInvalid,
    BudgetMode,
    BudgetVersionConflict,
    Price,
    SendRequest,
    Spend,
    evaluate,
    summarize,
)
from aiwebnovel.usage.persistence import ModelUsageAttemptRecord

PRICE_HISTORY = 10


class ModelPriceRevisionRecord(Base):
    __tablename__ = "model_price_revisions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_model_price_version"),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)", name="ck_model_price_currency"
        ),
        CheckConstraint(
            "input_micros_per_million BETWEEN 0 AND 100000000000"
            " AND output_micros_per_million BETWEEN 0 AND 100000000000",
            name="ck_model_price_amounts",
        ),
        UniqueConstraint("profile_id", "version", name="uq_model_price_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    input_micros_per_million: Mapped[int] = mapped_column(Integer, nullable=False)
    output_micros_per_million: Mapped[int] = mapped_column(Integer, nullable=False)
    cached_input_micros_per_million: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_write_micros_per_million: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectBudgetRevisionRecord(Base):
    __tablename__ = "project_budget_revisions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_project_budget_version"),
        CheckConstraint("mode IN ('off','warn','strict')", name="ck_project_budget_mode"),
        CheckConstraint(
            "(task_limit_micros IS NULL OR task_limit_micros BETWEEN 0 AND 100000000000000)"
            " AND (monthly_limit_micros IS NULL OR"
            " monthly_limit_micros BETWEEN 0 AND 100000000000000)",
            name="ck_project_budget_amounts",
        ),
        CheckConstraint(
            "mode = 'off' OR (currency IS NOT NULL AND length(currency) = 3"
            " AND currency = upper(currency)"
            " AND (task_limit_micros IS NOT NULL OR monthly_limit_micros IS NOT NULL))",
            name="ck_project_budget_complete",
        ),
        UniqueConstraint("project_id", "version", name="uq_project_budget_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    task_limit_micros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_limit_micros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelBudgetReservationRecord(Base):
    __tablename__ = "model_budget_reservations"
    __table_args__ = (
        CheckConstraint(
            "input_tokens_upper >= 0 AND output_tokens_upper >= 0 AND reserved_micros >= 0",
            name="ck_model_budget_reservation_counts",
        ),
        Index("ix_model_budget_reservations_project", "project_id", "task_id"),
    )
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_usage_attempts.id", ondelete="RESTRICT"), primary_key=True
    )
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    price_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_price_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    input_tokens_upper: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens_upper: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_micros: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _iso(value: datetime) -> str:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


def _price(record: ModelPriceRevisionRecord) -> Price:
    return Price(
        record.id,
        record.profile_id,
        record.version,
        record.currency,
        record.input_micros_per_million,
        record.output_micros_per_million,
        _iso(record.created_at),
        record.cached_input_micros_per_million,
        record.cache_write_micros_per_million,
    )


def _budget(record: ProjectBudgetRevisionRecord) -> Budget:
    mode: BudgetMode = (
        "strict" if record.mode == "strict" else ("warn" if record.mode == "warn" else "off")
    )
    return Budget(
        str(record.project_id),
        record.version,
        mode,
        record.currency,
        record.task_limit_micros,
        record.monthly_limit_micros,
        _iso(record.created_at),
    )


def month_start(now: datetime, zone: tzinfo | None) -> datetime:
    """The first instant of the author's local calendar month, in UTC."""
    local = now.astimezone(zone)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


_A = ModelUsageAttemptRecord
_RES = ModelBudgetReservationRecord
_P = ModelPriceRevisionRecord


class SqlAlchemyBudgetStore:
    def __init__(
        self,
        sessions: Callable[[], Session],
        projects: ProjectQueryService,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        zone: tzinfo | None = None,
    ) -> None:
        self._sessions = sessions
        self._projects = projects
        self._clock = clock
        self._zone = zone

    # -- reads used inside a caller's transaction -------------------------------------

    @staticmethod
    def current_price(session: Session, profile_id: str) -> Price | None:
        record = session.scalar(
            select(_P).where(_P.profile_id == profile_id).order_by(_P.version.desc()).limit(1)
        )
        return None if record is None else _price(record)

    @staticmethod
    def current_budget(session: Session, project_id: ProjectId) -> Budget | None:
        record = session.scalar(
            select(ProjectBudgetRevisionRecord)
            .where(ProjectBudgetRevisionRecord.project_id == project_id)
            .order_by(ProjectBudgetRevisionRecord.version.desc())
            .limit(1)
        )
        return None if record is None else _budget(record)

    @staticmethod
    def spend(
        session: Session,
        project_id: ProjectId,
        currency: str | None,
        *,
        task_id: str | None = None,
        since: datetime | None = None,
    ) -> Spend:
        conditions = [_A.project_id == project_id]
        if task_id is not None:
            conditions.append(_A.task_id == task_id)
        if since is not None:
            conditions.append(_A.started_at >= since)
        rows = session.execute(
            select(
                _A.status,
                _A.reported_input_tokens,
                _A.reported_output_tokens,
                _A.reported_total_tokens,
                _RES.reserved_micros,
                _RES.currency,
                _P.input_micros_per_million,
                _P.output_micros_per_million,
                _A.cached_input_tokens,
                _A.cache_write_tokens,
                _P.cached_input_micros_per_million,
                _P.cache_write_micros_per_million,
                _A.cache_details_status,
            )
            .select_from(_A)
            .outerjoin(_RES, _RES.attempt_id == _A.id)
            .outerjoin(_P, _P.id == _RES.price_revision_id)
            .where(*conditions)
        )
        return summarize((AttemptCost(*row) for row in rows), currency)

    def check(self, session: Session, project_id: ProjectId, request: SendRequest) -> BudgetCheck:
        price = self.current_price(session, request.profile_id)
        budget = self.current_budget(session, project_id)
        estimated = (
            None
            if price is None
            else price.cost(request.input_tokens_upper, request.output_tokens_upper)
        )
        currency = None if budget is None else budget.currency
        task = self.spend(session, project_id, currency, task_id=request.task_id[:36])
        month = self.spend(
            session, project_id, currency, since=month_start(self._clock(), self._zone)
        )
        decision, reasons = evaluate(budget, price, estimated, task, month)
        return BudgetCheck(budget, price, estimated, task, month, decision, reasons)

    def reserve(
        self,
        session: Session,
        attempt_id: str,
        project_id: ProjectId,
        request: SendRequest,
        price: Price | None,
        estimated: int | None,
    ) -> None:
        if price is None or estimated is None:
            return
        session.add(
            ModelBudgetReservationRecord(
                attempt_id=attempt_id,
                project_id=project_id,
                task_id=request.task_id[:36],
                price_revision_id=price.revision_id,
                currency=price.currency,
                input_tokens_upper=request.input_tokens_upper,
                output_tokens_upper=request.output_tokens_upper,
                reserved_micros=estimated,
                created_at=self._clock(),
            )
        )

    @staticmethod
    def resolve_project(session: Session, request: SendRequest) -> ProjectId | None:
        project_id = None if request.project_id is None else ProjectId.parse(request.project_id)
        if request.chapter_id is not None:
            owner = session.scalar(
                select(ChapterRecord.project_id).where(
                    ChapterRecord.id == ChapterId.parse(request.chapter_id)
                )
            )
            if owner is None or (project_id is not None and owner != project_id):
                return None
            project_id = owner
        return project_id

    # -- standalone operations ---------------------------------------------------------

    def _active(self, project_id: str) -> ProjectId:
        identifier = ProjectId.parse(project_id)
        if self._projects.get_project(GetProjectQuery(project_id)) is None:
            raise ProjectNotFound(identifier)
        return identifier

    def estimate(self, request: SendRequest) -> BudgetCheck:
        with self._sessions() as session:
            project_id = self.resolve_project(session, request)
            if project_id is None:
                raise BudgetInputInvalid
            return self.check(session, project_id, request)

    def price_history(self, profile_id: str) -> tuple[Price, ...]:
        with self._sessions() as session:
            return tuple(
                _price(record)
                for record in session.scalars(
                    select(_P)
                    .where(_P.profile_id == profile_id)
                    .order_by(_P.version.desc())
                    .limit(PRICE_HISTORY)
                )
            )

    def put_price(
        self,
        profile_id: str,
        expected_version: int,
        currency: str,
        input_micros: int,
        output_micros: int,
        cached_input_micros: int | None = None,
        cache_write_micros: int | None = None,
    ) -> None:
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            current = self.current_price(session, profile_id)
            if (0 if current is None else current.version) != expected_version:
                session.rollback()
                raise BudgetVersionConflict
            session.add(
                ModelPriceRevisionRecord(
                    id=str(uuid4()),
                    profile_id=profile_id,
                    version=expected_version + 1,
                    currency=currency,
                    input_micros_per_million=input_micros,
                    output_micros_per_million=output_micros,
                    cached_input_micros_per_million=cached_input_micros,
                    cache_write_micros_per_million=cache_write_micros,
                    created_at=self._clock(),
                )
            )
            session.commit()

    def budget_state(self, project_id: str) -> tuple[Budget | None, datetime, Spend]:
        identifier = self._active(project_id)
        start = month_start(self._clock(), self._zone)
        with self._sessions() as session:
            budget = self.current_budget(session, identifier)
            currency = None if budget is None else budget.currency
            return budget, start, self.spend(session, identifier, currency, since=start)

    def put_budget(
        self,
        project_id: str,
        expected_version: int,
        mode: BudgetMode,
        currency: str | None,
        task_limit: int | None,
        monthly_limit: int | None,
    ) -> None:
        identifier = self._active(project_id)
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            current = self.current_budget(session, identifier)
            if (0 if current is None else current.version) != expected_version:
                session.rollback()
                raise BudgetVersionConflict
            session.add(
                ProjectBudgetRevisionRecord(
                    id=str(uuid4()),
                    project_id=identifier,
                    version=expected_version + 1,
                    mode=mode,
                    currency=currency,
                    task_limit_micros=task_limit,
                    monthly_limit_micros=monthly_limit,
                    created_at=self._clock(),
                )
            )
            session.commit()
