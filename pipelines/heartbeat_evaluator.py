"""Heartbeat state machine for monitored page checks (JEG-339 / JEG-357).

Pure-Python, hermetic state machine. No DB, no network.

States:
    healthy, degraded, missed, error, disabled, unknown

Reads inputs in the form of a `CheckConfig` (schedule, ownership, thresholds)
and a sequence of `Observation` rows (already filtered by caller; evaluator
must not touch `live_page_checks`). Writes a `Heartbeat` snapshot.

Scheduling: spec calls for both `cadence_seconds` (fixed) and `cron_expr`
(via external cron parser). Cron resolution is delegated to a tiny internal
adapter `next_cron_fire` (uniformly-distributed synthetic schedule for tests;
production wiring can swap in croniter without touching this module).

Scheduler ownership: when the owning scheduler's last heartbeat is older than
its `down_grace_seconds`, scheduler is considered down; missed states from
this owner should be routed to platform/infra, not product on-call. This
module emits the boolean `scheduler_down` flag; routing decision lives in
the alert layer.

Soft dep: PagerDuty/Slack paging is stubbed via `pipeline_*` hooks (the spec
calls these out as TODO when the webhook is still PLACEHOLDER).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterable, List, Optional, Sequence


# ---- Enums (mirror monitoring.heartbeat_state / check_type / owner_type) ----


class HeartbeatState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    MISSED = "missed"
    ERROR = "error"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class CheckType(str, Enum):
    HTTP_STATUS = "http_status"
    HTTP_STATUS_AND_CONTENT = "http_status_and_content"
    RENDER_JS = "render_js"
    REDIRECT_OK = "redirect_ok"
    TLS_OK = "tls_ok"


class SchedulerOwnerType(str, Enum):
    PG_CRON = "pg_cron"
    GITHUB_ACTIONS = "github_actions"
    VERCEL_CRON = "vercel_cron"
    FLY_CRON = "fly_cron"
    EXTERNAL = "external"


class OwnershipStatus(str, Enum):
    OK = "ok"
    AMBIGUOUS = "ambiguous"
    UNKNOWN_OWNER = "unknown_owner"


# ---- Inputs ----


@dataclass(frozen=True)
class CheckConfig:
    check_id: str
    enabled: bool = True
    check_type: CheckType = CheckType.HTTP_STATUS
    cadence_seconds: Optional[int] = None
    cron_expr: Optional[str] = None
    grace_override_seconds: Optional[int] = None
    latency_budget_ms: Optional[int] = None
    scheduler_owner_type: SchedulerOwnerType = SchedulerOwnerType.PG_CRON
    scheduler_owner_id: str = "pg_cron_default"
    # number of distinct active ownership rows for this check. > 1 = ambiguous.
    active_ownership_count: int = 1


@dataclass(frozen=True)
class Observation:
    run_at: datetime
    ok: bool
    latency_ms: Optional[int] = None
    http_status: Optional[int] = None
    content_ok: Optional[bool] = None
    error_code: Optional[str] = None


@dataclass(frozen=True)
class SchedulerHeartbeat:
    scheduler_owner_type: SchedulerOwnerType
    scheduler_owner_id: str
    last_seen_at: datetime
    down_grace_seconds: int = 300


# ---- Outputs ----


@dataclass(frozen=True)
class Heartbeat:
    check_id: str
    state: HeartbeatState
    ownership_status: OwnershipStatus
    scheduler_down: bool
    state_reason: str
    expected_next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    last_ok_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    latest_details: dict = field(default_factory=dict)


# ---- Grace policy (JEG-357 §"Missed-Run Grace Policy") ----


GRACE_FLOOR_SECONDS = 120
GRACE_CEILING_SECONDS = 1800
GRACE_MULTIPLIER = 1.5


def grace_seconds_for_cadence(cadence_seconds: int) -> int:
    """clamp(round_up(1.5 × cadence), 120, 1800)."""
    if cadence_seconds <= 0:
        raise ValueError("cadence_seconds must be positive")
    raw = GRACE_MULTIPLIER * cadence_seconds
    rounded = int(math.ceil(raw))
    return max(GRACE_FLOOR_SECONDS, min(GRACE_CEILING_SECONDS, rounded))


def grace_seconds_for_cron(
    cron_expr: str,
    median_interval_seconds: Optional[int] = None,
) -> int:
    """For cron_expr: clamp(1.5 × median_interval, 120, 1800).

    `median_interval_seconds` is supplied by the caller (computed from the
    last 30 occurrences in production; tests pass a synthetic value).
    """
    if median_interval_seconds is None:
        # Production would compute this from the last 30 cron fires; without
        # that history, fall back to a reasonable default (10 min) so the
        # function still returns a clamped value.
        median_interval_seconds = 600
    raw = GRACE_MULTIPLIER * median_interval_seconds
    rounded = int(math.ceil(raw))
    return max(GRACE_FLOOR_SECONDS, min(GRACE_CEILING_SECONDS, rounded))


def effective_grace_seconds(cfg: CheckConfig) -> int:
    if cfg.grace_override_seconds is not None:
        if cfg.grace_override_seconds <= 0:
            raise ValueError("grace_override_seconds must be positive")
        return max(GRACE_FLOOR_SECONDS, min(GRACE_CEILING_SECONDS, cfg.grace_override_seconds))
    if cfg.cadence_seconds is not None:
        return grace_seconds_for_cadence(cfg.cadence_seconds)
    if cfg.cron_expr is not None:
        return grace_seconds_for_cron(cfg.cron_expr)
    raise ValueError("CheckConfig must specify cadence_seconds or cron_expr")


# ---- Schedule resolution ----


def expected_next_run_for_cadence(
    cadence_seconds: int,
    last_run_at: Optional[datetime],
    first_activation_at: Optional[datetime],
    now: datetime,
) -> datetime:
    """For fixed cadence: last_observed_run_at + cadence, floored at the
    first scheduled activation so a check that was bootstrapped long ago but
    has gone quiet does not snap to a stale anchor.
    """
    if cadence_seconds <= 0:
        raise ValueError("cadence_seconds must be positive")
    if last_run_at is None:
        if first_activation_at is None:
            return now
        # Round up to next cadence boundary from first_activation_at.
        delta = (now - first_activation_at).total_seconds()
        ticks = int(math.ceil(delta / cadence_seconds))
        return first_activation_at + timedelta(seconds=ticks * cadence_seconds)
    return last_run_at + timedelta(seconds=cadence_seconds)


def next_cron_fire(cron_expr: str, after: datetime) -> int:
    """Stub cron resolution. Tests use a synthetic cron whose interval is
    supplied via a special syntax: ``every:N`` → returns N seconds. Real
    production wires croniter here; this keeps the module hermetic.
    """
    if cron_expr.startswith("every:"):
        return int(cron_expr.split(":", 1)[1])
    raise ValueError(
        f"heartbeat_evaluator.next_cron_fire only understands synthetic cron "
        f"'every:<seconds>'. Got {cron_expr!r}. Wire croniter for production."
    )


def expected_next_run_for_cron(
    cron_expr: str,
    last_run_at: Optional[datetime],
    now: datetime,
) -> datetime:
    interval = next_cron_fire(cron_expr, now)
    if last_run_at is None:
        return now + timedelta(seconds=interval)
    return last_run_at + timedelta(seconds=interval)


def expected_next_run(
    cfg: CheckConfig,
    last_run_at: Optional[datetime],
    first_activation_at: Optional[datetime],
    now: datetime,
) -> datetime:
    if cfg.cadence_seconds is not None:
        return expected_next_run_for_cadence(
            cfg.cadence_seconds, last_run_at, first_activation_at, now
        )
    if cfg.cron_expr is not None:
        return expected_next_run_for_cron(cfg.cron_expr, last_run_at, now)
    raise ValueError("CheckConfig must specify cadence_seconds or cron_expr")


# ---- Scheduler-down detection ----


def scheduler_is_down(
    owner_type: SchedulerOwnerType,
    owner_id: str,
    heartbeats: Sequence[SchedulerHeartbeat],
    now: datetime,
) -> bool:
    matching = [
        h for h in heartbeats
        if h.scheduler_owner_type == owner_type and h.scheduler_owner_id == owner_id
    ]
    if not matching:
        # No heartbeat ever recorded → treat as down so we route to platform,
        # not product on-call. Spec: "until owners comply" fallback.
        return True
    latest = max(matching, key=lambda h: h.last_seen_at)
    grace = timedelta(seconds=latest.down_grace_seconds)
    return (now - latest.last_seen_at) > grace


def ownership_status_for(cfg: CheckConfig) -> OwnershipStatus:
    if cfg.active_ownership_count <= 0:
        return OwnershipStatus.UNKNOWN_OWNER
    if cfg.active_ownership_count > 1:
        return OwnershipStatus.AMBIGUOUS
    return OwnershipStatus.OK


# ---- State machine ----


def classify_observation(
    obs: Observation,
    check_type: CheckType,
    latency_budget_ms: Optional[int],
) -> HeartbeatState:
    """Classify a single observation against the check semantics in JEG-357."""
    if not obs.ok:
        return HeartbeatState.ERROR
    degraded = False
    if (
        latency_budget_ms is not None
        and obs.latency_ms is not None
        and obs.latency_ms > latency_budget_ms
    ):
        degraded = True
    if (
        check_type == CheckType.HTTP_STATUS_AND_CONTENT
        and obs.content_ok is False
    ):
        # Content mismatch with required check → hard error per spec.
        return HeartbeatState.ERROR
    if degraded:
        return HeartbeatState.DEGRADED
    return HeartbeatState.HEALTHY


def latest_observation(
    observations: Iterable[Observation],
    since: Optional[datetime] = None,
) -> Optional[Observation]:
    """Most recent observation, optionally restricted to >= since. Dedupe by
    run_at (keep max)."""
    latest: Optional[Observation] = None
    for obs in observations:
        if since is not None and obs.run_at < since:
            continue
        if latest is None or obs.run_at > latest.run_at:
            latest = obs
    return latest


def compute_state(
    cfg: CheckConfig,
    observations: Sequence[Observation],
    scheduler_heartbeats: Sequence[SchedulerHeartbeat],
    now: datetime,
    first_activation_at: Optional[datetime] = None,
) -> Heartbeat:
    """Top-level entry point. Mirrors monitoring.check_heartbeats row shape."""

    if not cfg.enabled:
        return Heartbeat(
            check_id=cfg.check_id,
            state=HeartbeatState.DISABLED,
            ownership_status=ownership_status_for(cfg),
            scheduler_down=False,
            state_reason="enabled=false",
        )

    has_schedule = cfg.cadence_seconds is not None or cfg.cron_expr is not None
    if not has_schedule:
        return Heartbeat(
            check_id=cfg.check_id,
            state=HeartbeatState.UNKNOWN,
            ownership_status=ownership_status_for(cfg),
            scheduler_down=False,
            state_reason="no schedule resolvable",
        )

    grace = effective_grace_seconds(cfg)
    last_run = latest_observation(observations)
    last_ok = latest_observation([o for o in observations if o.ok])
    last_err = latest_observation([o for o in observations if not o.ok])
    expected_next = expected_next_run(
        cfg,
        last_run.run_at if last_run else None,
        first_activation_at,
        now,
    )
    # Anchor the current window at NOW, not at the (stale) expected_next.
    # expected_next_run_for_cadence returns last_run + cadence, which is
    # anchored at the last observation; if the check has gone quiet,
    # expected_next stays stale and last_run would always fall inside its
    # own [window_start, now] window — making "not runs_in_window" impossible
    # to satisfy and the missed state unreachable (JEG-357).
    window_start = now - timedelta(seconds=grace)

    s_down = scheduler_is_down(
        cfg.scheduler_owner_type, cfg.scheduler_owner_id, scheduler_heartbeats, now
    )

    runs_in_window = [o for o in observations if window_start <= o.run_at <= now]
    latest_in_window = latest_observation(runs_in_window)

    own = ownership_status_for(cfg)

    # Transition conditions (deterministic order from spec):
    # 1. Failed run in current window → error
    if latest_in_window is not None and not latest_in_window.ok:
        return Heartbeat(
            check_id=cfg.check_id,
            state=HeartbeatState.ERROR,
            ownership_status=own,
            scheduler_down=s_down,
            state_reason="failed run in window",
            expected_next_run_at=expected_next,
            last_run_at=last_run.run_at if last_run else None,
            last_ok_at=last_ok.run_at if last_ok else None,
            last_error_at=last_err.run_at if last_err else None,
            latest_details={
                "error_code": latest_in_window.error_code,
                "http_status": latest_in_window.http_status,
                "latency_ms": latest_in_window.latency_ms,
            },
        )

    # 2. Missed: gap since last_run exceeds grace and no run in current window.
    # The window is anchored at now (see above), so a gap > grace implies an
    # empty window — but keep the explicit `not runs_in_window` check per spec.
    if (
        last_run is not None
        and (now - last_run.run_at) > timedelta(seconds=grace)
        and not runs_in_window
    ):
        reason = "no runs in window"
        if s_down:
            reason = "no runs in window; scheduler_down=true → route to platform"
        return Heartbeat(
            check_id=cfg.check_id,
            state=HeartbeatState.MISSED,
            ownership_status=own,
            scheduler_down=s_down,
            state_reason=reason,
            expected_next_run_at=expected_next,
            last_run_at=last_run.run_at if last_run else None,
            last_ok_at=last_ok.run_at if last_ok else None,
            last_error_at=last_err.run_at if last_err else None,
            latest_details={"grace_seconds": grace},
        )

    # 3. Latest ok run classified by degraded criteria
    if last_run is not None and last_run.ok:
        state = classify_observation(
            last_run, cfg.check_type, cfg.latency_budget_ms
        )
        return Heartbeat(
            check_id=cfg.check_id,
            state=state,
            ownership_status=own,
            scheduler_down=s_down,
            state_reason=f"latest ok run ({state.value})",
            expected_next_run_at=expected_next,
            last_run_at=last_run.run_at,
            last_ok_at=last_ok.run_at if last_ok else None,
            last_error_at=last_err.run_at if last_err else None,
            latest_details={
                "latency_ms": last_run.latency_ms,
                "http_status": last_run.http_status,
            },
        )

    # 4. No observation at all yet → unknown
    return Heartbeat(
        check_id=cfg.check_id,
        state=HeartbeatState.UNKNOWN,
        ownership_status=own,
        scheduler_down=s_down,
        state_reason="no observations yet",
        expected_next_run_at=expected_next,
        last_run_at=None,
        last_ok_at=None,
        last_error_at=None,
        latest_details={"grace_seconds": grace},
    )


# ---- Paging hook stub ---------------------------------------------------
#
# Spec: "stub the paging hook with a clear TODO" while Slack webhook is
# PLACEHOLDER. This module records what *would* be paged; the alert routing
# layer (separate module, also gated on the Slack webhook) reads the record.


@dataclass(frozen=True)
class PagePlan:
    """What *would* be paged. The real Slack/PagerDuty call lives elsewhere."""

    check_id: str
    state: HeartbeatState
    audience: str  # "product" | "platform"
    reason: str


def plan_pages(heartbeat: Heartbeat) -> List[PagePlan]:
    """Return a list of paging intents for this heartbeat.

    TODO(jeg339): Replace with a real Slack/PagerDuty call once the Slack
    webhook is no longer PLACEHOLDER (per JEG-379 soft-dep).
    """
    plans: List[PagePlan] = []
    state = heartbeat.state
    if state == HeartbeatState.DISABLED:
        return plans
    if state == HeartbeatState.UNKNOWN:
        return plans
    if state == HeartbeatState.DEGRADED:
        return plans  # Slack warning only; no page
    if state == HeartbeatState.ERROR:
        plans.append(PagePlan(
            check_id=heartbeat.check_id,
            state=state,
            audience="product",
            reason=heartbeat.state_reason,
        ))
    elif state == HeartbeatState.MISSED:
        if heartbeat.scheduler_down:
            plans.append(PagePlan(
                check_id=heartbeat.check_id,
                state=state,
                audience="platform",
                reason="scheduler_down aggregate",
            ))
        else:
            plans.append(PagePlan(
                check_id=heartbeat.check_id,
                state=state,
                audience="product",
                reason=heartbeat.state_reason,
            ))
    if heartbeat.ownership_status == OwnershipStatus.AMBIGUOUS:
        plans.append(PagePlan(
            check_id=heartbeat.check_id,
            state=HeartbeatState.ERROR,
            audience="platform",
            reason="ownership_ambiguous",
        ))
    return plans


# ---- Aggregation helpers (for scheduler-down aggregate alerts) ----


def aggregate_platform_missed(heartbeats: Sequence[Heartbeat]) -> List[str]:
    """Return check_ids for a single consolidated platform alert. Per spec:
    'Missed alerts per owner aggregate into a single incident with affected
    check IDs list when scheduler_down is true.'
    """
    return [
        h.check_id for h in heartbeats
        if h.state == HeartbeatState.MISSED and h.scheduler_down
    ]


# ---- Public surface (re-exports for callers/tests) ----


__all__ = [
    "HeartbeatState",
    "CheckType",
    "SchedulerOwnerType",
    "OwnershipStatus",
    "CheckConfig",
    "Observation",
    "SchedulerHeartbeat",
    "Heartbeat",
    "PagePlan",
    "grace_seconds_for_cadence",
    "grace_seconds_for_cron",
    "effective_grace_seconds",
    "expected_next_run_for_cadence",
    "expected_next_run_for_cron",
    "expected_next_run",
    "scheduler_is_down",
    "ownership_status_for",
    "classify_observation",
    "latest_observation",
    "compute_state",
    "plan_pages",
    "aggregate_platform_missed",
    "GRACE_FLOOR_SECONDS",
    "GRACE_CEILING_SECONDS",
    "GRACE_MULTIPLIER",
]