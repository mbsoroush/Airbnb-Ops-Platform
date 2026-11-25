"""The Airbnb Ops dashboard, defined as data (dashboard-as-code).

Every card reads the materialized view only; none touches `core`. Layout uses Metabase's
24-column grid. Edit this file and re-run `airbnb-ops metabase-setup` to update Metabase.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..constants import VIEW

GRID_WIDTH = 24
COLLECTION_NAME = "Airbnb Ops"
DASHBOARD_NAME = "Airbnb Ops - Neighbourhood Overview"


@dataclass
class CardSpec:
    name: str
    sql: str
    display: str
    row: int
    col: int
    width: int
    height: int
    visualization_settings: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class DashboardSpec:
    name: str
    collection: str
    description: str
    cards: tuple[CardSpec, ...]


def _chart(dimension: str, *metrics: str) -> dict[str, Any]:
    return {"graph.dimensions": [dimension], "graph.metrics": list(metrics)}


def default_dashboard() -> DashboardSpec:
    cards = (
        CardSpec(
            name="Data freshness (last view refresh)",
            description="When the materialized view was last built or refreshed.",
            sql=f"SELECT MAX(refreshed_at) AS last_refreshed FROM {VIEW}",
            display="scalar",
            row=0, col=0, width=24, height=3,
        ),
        CardSpec(
            name="Listings by neighbourhood",
            sql=(
                "SELECT neighbourhood, num_listings\n"
                f"FROM {VIEW}\n"
                "ORDER BY num_listings DESC"
            ),
            display="row",
            row=3, col=0, width=12, height=10,
            visualization_settings=_chart("neighbourhood", "num_listings"),
        ),
        CardSpec(
            name="Average and median price by neighbourhood",
            description=(
                "The average is sensitive to a few extreme listings, so compare it with the "
                "median. About a third of Munich listings have no price."
            ),
            sql=(
                "SELECT neighbourhood, avg_price, median_price\n"
                f"FROM {VIEW}\n"
                "ORDER BY avg_price DESC NULLS LAST"
            ),
            display="row",
            row=3, col=12, width=12, height=10,
            visualization_settings=_chart("neighbourhood", "avg_price", "median_price"),
        ),
        CardSpec(
            name="Review activity by neighbourhood",
            sql=(
                "SELECT neighbourhood, total_reviews\n"
                f"FROM {VIEW}\n"
                "ORDER BY total_reviews DESC"
            ),
            display="row",
            row=13, col=0, width=12, height=10,
            visualization_settings=_chart("neighbourhood", "total_reviews"),
        ),
        CardSpec(
            name="Availability rate by neighbourhood (%)",
            description="Share of days available: next 30 days and the full year.",
            sql=(
                "SELECT neighbourhood,\n"
                "       ROUND(availability_30_rate * 100, 1) AS availability_30_pct,\n"
                "       ROUND(availability_365_rate * 100, 1) AS availability_365_pct\n"
                f"FROM {VIEW}\n"
                "ORDER BY availability_365_pct DESC NULLS LAST"
            ),
            display="row",
            row=13, col=12, width=12, height=10,
            visualization_settings=_chart(
                "neighbourhood", "availability_30_pct", "availability_365_pct"
            ),
        ),
        CardSpec(
            name="Top neighbourhoods",
            sql=(
                "SELECT neighbourhood, num_listings, avg_price, median_price, total_reviews,\n"
                "       reviews_per_listing,\n"
                "       ROUND(availability_30_rate * 100, 1) AS availability_30_pct,\n"
                "       ROUND(availability_365_rate * 100, 1) AS availability_365_pct\n"
                f"FROM {VIEW}\n"
                "ORDER BY num_listings DESC\n"
                "LIMIT 10"
            ),
            display="table",
            row=23, col=0, width=24, height=9,
        ),
    )
    return DashboardSpec(
        name=DASHBOARD_NAME,
        collection=COLLECTION_NAME,
        description="Neighbourhood metrics from analytics.mv_airbnb_neighbourhood_summary.",
        cards=cards,
    )
