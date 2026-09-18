"""Deterministic revenue-prioritisation scoring logic (Gate 7).

The rule set below is copied verbatim from
CLAUDE_BUILD_BRIEF_SALESFORCE_GEMINI_MCP.md section 8 ("Gate 6 -- Second MCP
server")'s example policy:

    +3 Opportunity amount > GBP250k
    +2 Close date within 30 days
    +2 Strategic account
    +2 No meaningful activity for >14 days
    +1 Stage is Proposal or Negotiation

One deliberate substitution: the brief's threshold is GBP250k, but every
other gate in this repo (Gate 3's demo question, Gate 5/6's acceptance
tests, the org's own seeded sample data) has consistently used a $250k USD
threshold against a USD-denominated org -- there was never a GBP amount
anywhere in this project to begin with. Using $250,000 here keeps this
gate consistent with that established convention rather than introducing a
currency this repo has never actually used.

This module is plain Python, committed with the application -- deliberately
not a YAML/JSON rules file, a database table, or a rules-engine product.
There is nothing here a config format would buy that a typed, testable
Python function doesn't already give for free, and one fewer dependency /
parsing failure mode to worry about (see docs/decisions/ADR-004 for the
fuller rationale). Nothing in this module talks to Salesforce, Gemini, or
any network -- every input is a fact the *caller* (the agent, having
already retrieved it from Salesforce MCP) supplies; this module only ever
reasons about numbers and strings it's handed.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

AMOUNT_THRESHOLD_USD = 250_000.0
AMOUNT_THRESHOLD_POINTS = 3

CLOSE_DATE_WINDOW_DAYS = 30
CLOSE_DATE_POINTS = 2

STRATEGIC_ACCOUNT_POINTS = 2

STALE_ACTIVITY_THRESHOLD_DAYS = 14
STALE_ACTIVITY_POINTS = 2

# Exact StageName values used by this org (salesforce/sample-data/opportunities.csv),
# matched case-insensitively so "proposal/price quote" or "PROPOSAL/PRICE QUOTE"
# still applies -- the rule is about the stage's *meaning*, not its exact casing.
PRIORITY_STAGES = {"proposal/price quote", "negotiation/review"}
PRIORITY_STAGE_POINTS = 1

MAX_POSSIBLE_SCORE = (
    AMOUNT_THRESHOLD_POINTS + CLOSE_DATE_POINTS + STRATEGIC_ACCOUNT_POINTS
    + STALE_ACTIVITY_POINTS + PRIORITY_STAGE_POINTS
)


class InvalidOpportunityFactsError(ValueError):
    """Raised for malformed/out-of-range inputs -- never silently scored."""


@dataclass(frozen=True)
class ScoringFactor:
    rule: str
    applied: bool
    points: int
    detail: str


@dataclass(frozen=True)
class ScoringResult:
    score: int
    max_possible_score: int
    factors: list[ScoringFactor] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "max_possible_score": self.max_possible_score,
            "factors": [
                {"rule": f.rule, "applied": f.applied, "points": f.points, "detail": f.detail}
                for f in self.factors
            ],
            "explanation": self.explanation,
        }


def get_policy_rules() -> dict:
    """Returns the fixed rule catalogue itself, verbatim -- lets a caller (the
    agent, a human, a test) see and cite exactly what this gate's policy is,
    rather than having to infer it from score_opportunity()'s behaviour."""
    return {
        "source": "CLAUDE_BUILD_BRIEF_SALESFORCE_GEMINI_MCP.md section 8, Gate 6 example policy",
        "max_possible_score": MAX_POSSIBLE_SCORE,
        "rules": [
            {
                "rule": "amount_over_threshold",
                "points": AMOUNT_THRESHOLD_POINTS,
                "description": f"Opportunity amount is greater than ${AMOUNT_THRESHOLD_USD:,.0f}.",
            },
            {
                "rule": "close_date_within_window",
                "points": CLOSE_DATE_POINTS,
                "description": f"Close date is within the next {CLOSE_DATE_WINDOW_DAYS} days.",
            },
            {
                "rule": "strategic_account",
                "points": STRATEGIC_ACCOUNT_POINTS,
                "description": "Account is flagged as strategic.",
            },
            {
                "rule": "stale_activity",
                "points": STALE_ACTIVITY_POINTS,
                "description": f"No meaningful activity for more than {STALE_ACTIVITY_THRESHOLD_DAYS} days.",
            },
            {
                "rule": "priority_stage",
                "points": PRIORITY_STAGE_POINTS,
                "description": "Stage is Proposal/Price Quote or Negotiation/Review.",
            },
        ],
    }


def _parse_close_date(close_date: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(close_date)
    except ValueError as exc:
        raise InvalidOpportunityFactsError(
            f"close_date must be an ISO date string (YYYY-MM-DD), got {close_date!r}."
        ) from exc


def score_opportunity(
    *,
    amount: float,
    stage: str,
    days_since_activity: int,
    is_strategic_account: bool,
    close_date: str | None = None,
    as_of_date: str | None = None,
) -> ScoringResult:
    """Deterministic score for one opportunity's already-retrieved facts.

    Every argument is a fact about a single opportunity -- this function
    does not look anything up, so the same inputs always produce the same
    output (AT-07-02). Invalid inputs raise InvalidOpportunityFactsError
    rather than silently producing a score for nonsensical facts (AT-07-03).

    `as_of_date` (ISO date string) exists only so the close-date-window rule
    is testable without depending on the real wall-clock date; callers
    normally omit it and get today's date.
    """
    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        raise InvalidOpportunityFactsError(f"amount must be numeric, got {amount!r}.")
    if amount < 0:
        raise InvalidOpportunityFactsError(f"amount cannot be negative, got {amount!r}.")

    if not isinstance(stage, str) or not stage.strip():
        raise InvalidOpportunityFactsError(f"stage must be a non-empty string, got {stage!r}.")

    if not isinstance(days_since_activity, int) or isinstance(days_since_activity, bool):
        raise InvalidOpportunityFactsError(
            f"days_since_activity must be an integer, got {days_since_activity!r}."
        )
    if days_since_activity < 0:
        raise InvalidOpportunityFactsError(
            f"days_since_activity cannot be negative, got {days_since_activity!r}."
        )

    if not isinstance(is_strategic_account, bool):
        raise InvalidOpportunityFactsError(
            f"is_strategic_account must be a boolean, got {is_strategic_account!r}."
        )

    reference_date = _parse_close_date(as_of_date) if as_of_date else datetime.date.today()

    factors: list[ScoringFactor] = []

    amount_applies = amount > AMOUNT_THRESHOLD_USD
    factors.append(
        ScoringFactor(
            rule="amount_over_threshold",
            applied=amount_applies,
            points=AMOUNT_THRESHOLD_POINTS if amount_applies else 0,
            detail=f"Amount ${amount:,.0f} {'exceeds' if amount_applies else 'does not exceed'} "
            f"${AMOUNT_THRESHOLD_USD:,.0f}.",
        )
    )

    close_date_applies = False
    close_date_detail = "No close date supplied."
    if close_date is not None:
        parsed_close_date = _parse_close_date(close_date)
        days_until_close = (parsed_close_date - reference_date).days
        close_date_applies = 0 <= days_until_close <= CLOSE_DATE_WINDOW_DAYS
        close_date_detail = (
            f"Close date {close_date} is {days_until_close} day(s) from {reference_date.isoformat()} "
            f"({'within' if close_date_applies else 'outside'} the {CLOSE_DATE_WINDOW_DAYS}-day window)."
        )
    factors.append(
        ScoringFactor(
            rule="close_date_within_window",
            applied=close_date_applies,
            points=CLOSE_DATE_POINTS if close_date_applies else 0,
            detail=close_date_detail,
        )
    )

    factors.append(
        ScoringFactor(
            rule="strategic_account",
            applied=is_strategic_account,
            points=STRATEGIC_ACCOUNT_POINTS if is_strategic_account else 0,
            detail="Account is flagged as strategic." if is_strategic_account else "Account is not flagged as strategic.",
        )
    )

    stale_applies = days_since_activity > STALE_ACTIVITY_THRESHOLD_DAYS
    factors.append(
        ScoringFactor(
            rule="stale_activity",
            applied=stale_applies,
            points=STALE_ACTIVITY_POINTS if stale_applies else 0,
            detail=f"{days_since_activity} day(s) since last activity "
            f"({'over' if stale_applies else 'within'} the {STALE_ACTIVITY_THRESHOLD_DAYS}-day threshold).",
        )
    )

    stage_applies = stage.strip().lower() in PRIORITY_STAGES
    factors.append(
        ScoringFactor(
            rule="priority_stage",
            applied=stage_applies,
            points=PRIORITY_STAGE_POINTS if stage_applies else 0,
            detail=f"Stage {stage!r} {'is' if stage_applies else 'is not'} Proposal/Price Quote or Negotiation/Review.",
        )
    )

    total_score = sum(f.points for f in factors)
    applied_rules = [f.rule for f in factors if f.applied]
    explanation = (
        f"Score {total_score}/{MAX_POSSIBLE_SCORE}: "
        + (", ".join(applied_rules) if applied_rules else "no prioritisation rules matched")
        + "."
    )

    return ScoringResult(
        score=total_score,
        max_possible_score=MAX_POSSIBLE_SCORE,
        factors=factors,
        explanation=explanation,
    )
