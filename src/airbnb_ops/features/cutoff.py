"""Cutoff-date logic (pure). The cutoff separates feature windows from the label window.

Windows (all dates inclusive):
    history   cutoff - 89 .. cutoff      (90 days, `*_last_90d` features)
    recent    cutoff - 29 .. cutoff      (30 days, `*_last_30d` features)
    label     cutoff + 1  .. cutoff + 30 (30 days, `future_*` columns and the target)

The earliest valid cutoff is calendar_min + 90 days (the assignment's formula; it leaves one
spare day at the start of the calendar) and the latest is calendar_max - 30 days.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .config import FeatureConfig


@dataclass(frozen=True)
class CutoffPlan:
    cutoff_date: date
    history_start_date: date
    recent_start_date: date
    label_end_date: date
    earliest_valid_cutoff: date
    latest_valid_cutoff: date
    selection_rule: str
    selection_reason: str

    def as_dict(self) -> dict[str, str]:
        return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in vars(self).items()}


def plan_cutoff(calendar_min: date, calendar_max: date, config: FeatureConfig) -> CutoffPlan:
    """Choose and validate the cutoff. Raises ValueError if the calendar is too short."""
    earliest = calendar_min + timedelta(days=config.past_window_days)
    latest = calendar_max - timedelta(days=config.future_window_days)
    if earliest > latest:
        raise ValueError(
            f"Calendar {calendar_min}..{calendar_max} is too short for a "
            f"{config.past_window_days} day history and a {config.future_window_days} day label"
        )

    if config.cutoff_date is None:
        cutoff = earliest
        rule = "earliest_valid"
        reason = (
            f"Earliest valid cutoff (calendar start + {config.past_window_days} days), "
            "derived from the data."
        )
    else:
        cutoff = config.cutoff_date
        rule = "configured"
        reason = config.cutoff_reason or "Cutoff date set explicitly."
        if not earliest <= cutoff <= latest:
            raise ValueError(f"Cutoff {cutoff} is outside the valid range {earliest}..{latest}")

    return CutoffPlan(
        cutoff_date=cutoff,
        history_start_date=cutoff - timedelta(days=config.past_window_days - 1),
        recent_start_date=cutoff - timedelta(days=config.recent_window_days - 1),
        label_end_date=cutoff + timedelta(days=config.future_window_days),
        earliest_valid_cutoff=earliest,
        latest_valid_cutoff=latest,
        selection_rule=rule,
        selection_reason=reason,
    )
