"""Story control HTTP: author-entered plans, plot threads, timeline and recall; no model calls."""

from collections.abc import Callable
from typing import Annotated, get_args

from fastapi import APIRouter, Depends, Request, Response

from aiwebnovel.ai_writing.web import map_error, require_json
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import DomainError, InvalidDomainIdentifier
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.story_control.foreshadow import ForeshadowExtractionService
from aiwebnovel.story_control.foreshadow_models import (
    AdoptForeshadowCards,
    EditForeshadowCard,
    ForeshadowCardInvalid,
    ForeshadowConflict,
    ForeshadowConsentRequired,
    ForeshadowInvalid,
    ForeshadowNotFound,
    ForeshadowOutputInvalid,
    ForeshadowProposalList,
    ForeshadowProposalView,
    ForeshadowStale,
    ForeshadowUndoConflict,
    PrepareExtraction,
    PreviewRange,
    RangePreview,
    SendExtraction,
    UndoForeshadowAdoption,
)
from aiwebnovel.story_control.models import (
    ArcPlan,
    ChapterGuide,
    Event,
    FactSearchPage,
    Goal,
    RecallPinsInvalid,
    RecallPolicyState,
    RecallPreview,
    RecallPreviewInput,
    SaveEvent,
    SaveGoal,
    SaveRecallPolicy,
    SaveState,
    SaveThread,
    State,
    StoryControlConflict,
    StoryControlCycle,
    StoryControlInvalid,
    StoryControlNotFound,
    Thread,
    ThreadStatus,
    Timeline,
)
from aiwebnovel.story_control.proposal_models import (
    AdoptCards,
    EditCard,
    PlanProposalCardInvalid,
    PlanProposalConflict,
    PlanProposalConsentRequired,
    PlanProposalInvalid,
    PlanProposalList,
    PlanProposalNotFound,
    PlanProposalOutputInvalid,
    PlanProposalStale,
    PlanProposalUndoConflict,
    PlanProposalView,
    PrepareProposal,
    SendProposal,
    UndoAdoption,
)
from aiwebnovel.story_control.proposals import PlanProposalService
from aiwebnovel.story_control.service import StoryControlService
from aiwebnovel.usage.budget import SendEstimate

_MAX_OFFSET = 1_000_000
_ERRORS: dict[type[DomainError], tuple[int, str]] = {
    StoryControlConflict: (409, "STORY_CONTROL_CONFLICT"),
    StoryControlInvalid: (422, "STORY_CONTROL_INVALID"),
    StoryControlNotFound: (404, "STORY_CONTROL_NOT_FOUND"),
    StoryControlCycle: (422, "STORY_CONTROL_CYCLE"),
    RecallPinsInvalid: (409, "AI_RECALL_PINS_INVALID"),
    PlanProposalConflict: (409, "PLAN_PROPOSAL_CONFLICT"),
    PlanProposalStale: (409, "PLAN_PROPOSAL_STALE"),
    PlanProposalInvalid: (422, "PLAN_PROPOSAL_INVALID"),
    PlanProposalNotFound: (404, "PLAN_PROPOSAL_NOT_FOUND"),
    PlanProposalConsentRequired: (403, "PLAN_PROPOSAL_CONSENT_REQUIRED"),
    PlanProposalOutputInvalid: (422, "PLAN_PROPOSAL_OUTPUT_INVALID"),
    PlanProposalCardInvalid: (422, "PLAN_PROPOSAL_CARD_INVALID"),
    PlanProposalUndoConflict: (409, "PLAN_PROPOSAL_UNDO_CONFLICT"),
    ForeshadowConflict: (409, "FORESHADOW_EXTRACTION_CONFLICT"),
    ForeshadowStale: (409, "FORESHADOW_EXTRACTION_STALE"),
    ForeshadowInvalid: (422, "FORESHADOW_EXTRACTION_INVALID"),
    ForeshadowCardInvalid: (422, "FORESHADOW_CARD_INVALID"),
    ForeshadowNotFound: (404, "FORESHADOW_EXTRACTION_NOT_FOUND"),
    ForeshadowConsentRequired: (403, "FORESHADOW_EXTRACTION_CONSENT_REQUIRED"),
    ForeshadowOutputInvalid: (422, "FORESHADOW_EXTRACTION_OUTPUT_INVALID"),
    ForeshadowUndoConflict: (409, "FORESHADOW_UNDO_CONFLICT"),
}


def get_story_control_service(request: Request) -> StoryControlService:
    if getattr(request.app.state, "ai_workflow_schema_required", False):
        raise AppError(
            code="AI_WORKFLOW_SCHEMA_REQUIRED",
            message="Back up and explicitly upgrade the database to use story planning.",
            status_code=503,
        )
    service = getattr(request.app.state, "story_control_service", None)
    if not isinstance(service, StoryControlService):
        raise AppError(
            code="STORY_CONTROL_UNAVAILABLE",
            message="Story planning is unavailable.",
            status_code=503,
        )
    return service


def get_plan_proposal_service(request: Request) -> PlanProposalService:
    proposals = get_story_control_service(request).proposal_service
    if not isinstance(proposals, PlanProposalService):
        raise AppError(
            code="STORY_CONTROL_UNAVAILABLE",
            message="Story planning is unavailable.",
            status_code=503,
        )
    return proposals


def get_foreshadow_service(request: Request) -> ForeshadowExtractionService:
    extractions = get_story_control_service(request).foreshadow_service
    if not isinstance(extractions, ForeshadowExtractionService):
        raise AppError(
            code="STORY_CONTROL_UNAVAILABLE",
            message="Story planning is unavailable.",
            status_code=503,
        )
    return extractions


def _invoke[T](response: Response, action: Callable[[], T], *, project: bool = False) -> T:
    response.headers["Cache-Control"] = "no-store"
    try:
        return action()
    except ProjectNotFound:
        raise AppError(
            code="PROJECT_NOT_FOUND", message="Project not found.", status_code=404
        ) from None
    except InvalidDomainIdentifier as error:
        if project:
            raise AppError(
                code="INVALID_PROJECT_ID",
                message="The Project identifier is invalid.",
                status_code=422,
            ) from None
        raise map_error(error) from None
    except DomainError as error:
        if type(error) in _ERRORS:
            status, code = _ERRORS[type(error)]
            raise AppError(code=code, message=error.message, status_code=status) from None
        raise map_error(error) from None


def _invalid_query() -> AppError:
    return AppError(
        code="INVALID_STORY_CONTROL_QUERY",
        message="The story planning query parameters are invalid.",
        status_code=422,
    )


def _single(request: Request, name: str, maximum: int = 60) -> str | None:
    values = request.query_params.getlist(name)
    if not values:
        return None
    if len(values) > 1 or not 1 <= len(values[0]) <= maximum:
        raise _invalid_query()
    return values[0]


def _integer(request: Request, name: str, default: int, maximum: int, minimum: int) -> int:
    raw = _single(request, name, 7)
    if raw is None:
        return default
    if not raw.isascii() or not raw.isdecimal():
        raise _invalid_query()
    value = int(raw, 10)
    if not minimum <= value <= maximum:
        raise _invalid_query()
    return value


def _only(request: Request, allowed: frozenset[str]) -> None:
    if any(key not in allowed for key in request.query_params):
        raise _invalid_query()


_THREAD_STATUSES = frozenset(get_args(ThreadStatus))
_FACT_STATUSES = frozenset({"pending", "confirmed", "rejected"})


def get_timeline_query(request: Request) -> tuple[str | None, str | None, ThreadStatus | None]:
    _only(request, frozenset({"character_id", "volume_id", "status"}))
    status = _single(request, "status")
    if status is not None and status not in _THREAD_STATUSES:
        raise _invalid_query()
    return (
        _single(request, "character_id"),
        _single(request, "volume_id"),
        status,  # type: ignore[return-value]
    )


def get_fact_query(request: Request) -> dict[str, object]:
    _only(request, frozenset({"q", "chapter_id", "status", "for_chapter", "offset", "limit"}))
    status = _single(request, "status")
    if status is not None and status not in _FACT_STATUSES:
        raise _invalid_query()
    query = request.query_params.getlist("q")
    if len(query) > 1 or (query and len(query[0]) > 100):
        raise _invalid_query()
    return {
        "query": query[0] if query else "",
        "chapter_id": _single(request, "chapter_id"),
        "status": status,
        "for_chapter": _single(request, "for_chapter"),
        "offset": _integer(request, "offset", 0, _MAX_OFFSET, 0),
        "limit": _integer(request, "limit", 50, 100, 1),
    }


Service = Annotated[StoryControlService, Depends(get_story_control_service)]
Json = Annotated[None, Depends(require_json)]
Proposals = Annotated[PlanProposalService, Depends(get_plan_proposal_service)]
Extractions = Annotated[ForeshadowExtractionService, Depends(get_foreshadow_service)]


def create_story_control_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix, tags=["Story Control"])
    project = "/projects/{project_id}"

    @router.get(project + "/arc-plans", response_model=ArcPlan)
    def arc_plan(project_id: str, response: Response, service: Service) -> ArcPlan:
        return _invoke(response, lambda: service.arc_plan(project_id), project=True)

    @router.post(project + "/arc-plans", response_model=Goal, status_code=201)
    def create_goal(
        project_id: str, payload: SaveGoal, response: Response, service: Service, _json: Json
    ) -> Goal:
        return _invoke(response, lambda: service.save_goal(project_id, None, payload), project=True)

    @router.put(project + "/arc-plans/{goal_id}", response_model=Goal)
    def update_goal(
        project_id: str,
        goal_id: str,
        payload: SaveGoal,
        response: Response,
        service: Service,
        _json: Json,
    ) -> Goal:
        return _invoke(
            response, lambda: service.save_goal(project_id, goal_id, payload), project=True
        )

    proposals = project + "/plan-proposals"

    @router.get(proposals, response_model=PlanProposalList)
    def list_proposals(project_id: str, response: Response, service: Proposals) -> PlanProposalList:
        return _invoke(
            response,
            lambda: PlanProposalList(
                project_id=project_id, items=service.list_proposals(project_id)
            ),
            project=True,
        )

    @router.post(proposals, response_model=PlanProposalView, status_code=201)
    def prepare_proposal(
        project_id: str,
        payload: PrepareProposal,
        response: Response,
        service: Proposals,
        _json: Json,
    ) -> PlanProposalView:
        # Freezes the goal, existing plans and chapter titles; no model request.
        return _invoke(
            response,
            lambda: service.prepare(
                project_id, payload.goal_id, payload.profile_id, payload.author_request
            ),
            project=True,
        )

    @router.get(proposals + "/{proposal_id}", response_model=PlanProposalView)
    def get_proposal(
        project_id: str, proposal_id: str, response: Response, service: Proposals
    ) -> PlanProposalView:
        return _invoke(response, lambda: service.get(project_id, proposal_id), project=True)

    @router.get(proposals + "/{proposal_id}/estimate", response_model=SendEstimate)
    def estimate_proposal(
        project_id: str, proposal_id: str, response: Response, service: Proposals
    ) -> SendEstimate:
        return _invoke(response, lambda: service.estimate(project_id, proposal_id), project=True)

    @router.post(proposals + "/{proposal_id}/send", response_model=PlanProposalView)
    def send_proposal(
        project_id: str,
        proposal_id: str,
        payload: SendProposal,
        response: Response,
        service: Proposals,
        _json: Json,
    ) -> PlanProposalView:
        return _invoke(
            response,
            lambda: service.send(
                project_id, proposal_id, payload.expected_version, payload.cloud_consent
            ),
            project=True,
        )

    @router.post(proposals + "/{proposal_id}/adopt", response_model=PlanProposalView)
    def adopt_proposal(
        project_id: str,
        proposal_id: str,
        payload: AdoptCards,
        response: Response,
        service: Proposals,
        _json: Json,
    ) -> PlanProposalView:
        return _invoke(
            response,
            lambda: service.adopt(project_id, proposal_id, payload.card_indexes),
            project=True,
        )

    @router.put(proposals + "/{proposal_id}/cards/{card_index}", response_model=PlanProposalView)
    def edit_proposal_card(
        project_id: str,
        proposal_id: str,
        card_index: int,
        payload: EditCard,
        response: Response,
        service: Proposals,
        _json: Json,
    ) -> PlanProposalView:
        # Stores the author's edit beside the untouched original card; writes no plan.
        return _invoke(
            response,
            lambda: service.edit_card(
                project_id, proposal_id, card_index, payload.expected_version, payload.card
            ),
            project=True,
        )

    @router.post(proposals + "/{proposal_id}/undo", response_model=PlanProposalView)
    def undo_proposal_card(
        project_id: str,
        proposal_id: str,
        payload: UndoAdoption,
        response: Response,
        service: Proposals,
        _json: Json,
    ) -> PlanProposalView:
        return _invoke(
            response,
            lambda: service.undo(
                project_id, proposal_id, payload.card_index, payload.expected_version
            ),
            project=True,
        )

    extractions = project + "/foreshadow-proposals"

    @router.get(extractions, response_model=ForeshadowProposalList)
    def list_extractions(
        project_id: str, response: Response, service: Extractions
    ) -> ForeshadowProposalList:
        return _invoke(
            response,
            lambda: ForeshadowProposalList(
                project_id=project_id, items=service.list_proposals(project_id)
            ),
            project=True,
        )

    @router.post(extractions + "/preview", response_model=RangePreview)
    def preview_extraction(
        project_id: str,
        payload: PreviewRange,
        response: Response,
        service: Extractions,
        _json: Json,
    ) -> RangePreview:
        # Lists the chosen chapters and their saved sizes; no model request, nothing stored.
        return _invoke(
            response, lambda: service.preview(project_id, payload.chapter_ids), project=True
        )

    @router.post(extractions, response_model=ForeshadowProposalView, status_code=201)
    def prepare_extraction(
        project_id: str,
        payload: PrepareExtraction,
        response: Response,
        service: Extractions,
        _json: Json,
    ) -> ForeshadowProposalView:
        # Freezes the chosen chapters' saved text and the open threads; no model request.
        return _invoke(
            response,
            lambda: service.prepare(
                project_id, payload.chapter_ids, payload.profile_id, payload.author_request
            ),
            project=True,
        )

    @router.get(extractions + "/{proposal_id}", response_model=ForeshadowProposalView)
    def get_extraction(
        project_id: str, proposal_id: str, response: Response, service: Extractions
    ) -> ForeshadowProposalView:
        return _invoke(response, lambda: service.get(project_id, proposal_id), project=True)

    @router.get(extractions + "/{proposal_id}/estimate", response_model=SendEstimate)
    def estimate_extraction(
        project_id: str, proposal_id: str, response: Response, service: Extractions
    ) -> SendEstimate:
        return _invoke(response, lambda: service.estimate(project_id, proposal_id), project=True)

    @router.post(extractions + "/{proposal_id}/send", response_model=ForeshadowProposalView)
    def send_extraction(
        project_id: str,
        proposal_id: str,
        payload: SendExtraction,
        response: Response,
        service: Extractions,
        _json: Json,
    ) -> ForeshadowProposalView:
        return _invoke(
            response,
            lambda: service.send(
                project_id, proposal_id, payload.expected_version, payload.cloud_consent
            ),
            project=True,
        )

    @router.post(extractions + "/{proposal_id}/adopt", response_model=ForeshadowProposalView)
    def adopt_extraction(
        project_id: str,
        proposal_id: str,
        payload: AdoptForeshadowCards,
        response: Response,
        service: Extractions,
        _json: Json,
    ) -> ForeshadowProposalView:
        return _invoke(
            response,
            lambda: service.adopt(project_id, proposal_id, payload.card_indexes),
            project=True,
        )

    @router.put(
        extractions + "/{proposal_id}/cards/{card_index}", response_model=ForeshadowProposalView
    )
    def edit_extraction_card(
        project_id: str,
        proposal_id: str,
        card_index: int,
        payload: EditForeshadowCard,
        response: Response,
        service: Extractions,
        _json: Json,
    ) -> ForeshadowProposalView:
        # Stores the author's edit beside the untouched original card; writes no thread.
        return _invoke(
            response,
            lambda: service.edit_card(
                project_id, proposal_id, card_index, payload.expected_version, payload.card
            ),
            project=True,
        )

    @router.post(extractions + "/{proposal_id}/undo", response_model=ForeshadowProposalView)
    def undo_extraction_card(
        project_id: str,
        proposal_id: str,
        payload: UndoForeshadowAdoption,
        response: Response,
        service: Extractions,
        _json: Json,
    ) -> ForeshadowProposalView:
        return _invoke(
            response,
            lambda: service.undo(
                project_id, proposal_id, payload.card_index, payload.expected_version
            ),
            project=True,
        )

    @router.get(project + "/timeline", response_model=Timeline)
    def timeline(
        project_id: str,
        response: Response,
        service: Service,
        query: Annotated[
            tuple[str | None, str | None, ThreadStatus | None], Depends(get_timeline_query)
        ],
    ) -> Timeline:
        return _invoke(response, lambda: service.timeline(project_id, *query), project=True)

    @router.post(project + "/plot-threads", response_model=Thread, status_code=201)
    def create_thread(
        project_id: str, payload: SaveThread, response: Response, service: Service, _json: Json
    ) -> Thread:
        return _invoke(
            response, lambda: service.save_thread(project_id, None, payload), project=True
        )

    @router.put(project + "/plot-threads/{thread_id}", response_model=Thread)
    def update_thread(
        project_id: str,
        thread_id: str,
        payload: SaveThread,
        response: Response,
        service: Service,
        _json: Json,
    ) -> Thread:
        return _invoke(
            response, lambda: service.save_thread(project_id, thread_id, payload), project=True
        )

    @router.post(project + "/story-events", response_model=Event, status_code=201)
    def create_event(
        project_id: str, payload: SaveEvent, response: Response, service: Service, _json: Json
    ) -> Event:
        return _invoke(
            response, lambda: service.save_event(project_id, None, payload), project=True
        )

    @router.put(project + "/story-events/{event_id}", response_model=Event)
    def update_event(
        project_id: str,
        event_id: str,
        payload: SaveEvent,
        response: Response,
        service: Service,
        _json: Json,
    ) -> Event:
        return _invoke(
            response, lambda: service.save_event(project_id, event_id, payload), project=True
        )

    @router.post(project + "/state-intervals", response_model=State, status_code=201)
    def create_state(
        project_id: str, payload: SaveState, response: Response, service: Service, _json: Json
    ) -> State:
        return _invoke(
            response, lambda: service.save_state(project_id, None, payload), project=True
        )

    @router.put(project + "/state-intervals/{state_id}", response_model=State)
    def update_state(
        project_id: str,
        state_id: str,
        payload: SaveState,
        response: Response,
        service: Service,
        _json: Json,
    ) -> State:
        return _invoke(
            response, lambda: service.save_state(project_id, state_id, payload), project=True
        )

    @router.get(project + "/facts/search", response_model=FactSearchPage)
    def search_facts(
        project_id: str,
        response: Response,
        service: Service,
        query: Annotated[dict[str, object], Depends(get_fact_query)],
    ) -> FactSearchPage:
        return _invoke(
            response,
            lambda: service.search_facts(project_id, **query),  # type: ignore[arg-type]
            project=True,
        )

    chapter = "/chapters/{chapter_id}"

    @router.get(chapter + "/story-guide", response_model=ChapterGuide)
    def guide(chapter_id: str, response: Response, service: Service) -> ChapterGuide:
        return _invoke(response, lambda: service.chapter_guide(chapter_id))

    def policy_state(chapter_id: str, service: StoryControlService) -> RecallPolicyState:
        policy = service.recall_policy(chapter_id)
        return RecallPolicyState(
            chapter_id=chapter_id,
            version=0 if policy is None else policy.version,
            pinned_fact_ids=[] if policy is None else policy.pinned_fact_ids,
            excluded_fact_ids=[] if policy is None else policy.excluded_fact_ids,
            updated_at=None if policy is None else policy.updated_at,
        )

    @router.get(chapter + "/recall-policy", response_model=RecallPolicyState)
    def recall_policy(chapter_id: str, response: Response, service: Service) -> RecallPolicyState:
        return _invoke(response, lambda: policy_state(chapter_id, service))

    @router.put(chapter + "/recall-policy", response_model=RecallPolicyState)
    def save_recall_policy(
        chapter_id: str,
        payload: SaveRecallPolicy,
        response: Response,
        service: Service,
        _json: Json,
    ) -> RecallPolicyState:
        def save() -> RecallPolicyState:
            service.save_recall_policy(chapter_id, payload)
            return policy_state(chapter_id, service)

        return _invoke(response, save)

    @router.post(chapter + "/recall-preview", response_model=RecallPreview)
    def recall_preview(
        chapter_id: str,
        payload: RecallPreviewInput,
        response: Response,
        service: Service,
        _json: Json,
    ) -> RecallPreview:
        return _invoke(response, lambda: service.recall_preview(chapter_id, payload))

    return router
