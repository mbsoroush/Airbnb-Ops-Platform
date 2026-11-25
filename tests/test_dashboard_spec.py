"""Static checks on the dashboard definition (no Metabase, no database)."""
import re

from typer.testing import CliRunner

from airbnb_ops.cli import app
from airbnb_ops.constants import VIEW
from airbnb_ops.metabase.dashboard import GRID_WIDTH, default_dashboard

SPEC = default_dashboard()
REQUIRED = {
    "Listings by neighbourhood",
    "Average and median price by neighbourhood",
    "Review activity by neighbourhood",
    "Availability rate by neighbourhood (%)",
    "Top neighbourhoods",
}


def test_required_cards_present_and_names_unique():
    names = [card.name for card in SPEC.cards]
    assert REQUIRED <= set(names)
    assert len(names) == len(set(names))


def test_cards_read_only_the_view():
    for card in SPEC.cards:
        sql = card.sql.lower()
        assert VIEW in sql, card.name
        assert "core." not in sql, card.name
        assert not re.search(r"select\s+\*", sql), card.name


def test_layout_fits_grid_and_does_not_overlap():
    seen: dict[tuple[int, int], str] = {}
    for card in SPEC.cards:
        assert card.col >= 0 and card.col + card.width <= GRID_WIDTH, card.name
        assert card.width > 0 and card.height > 0, card.name
        for row in range(card.row, card.row + card.height):
            for col in range(card.col, card.col + card.width):
                assert (row, col) not in seen, f"{card.name} overlaps {seen[(row, col)]}"
                seen[(row, col)] = card.name


def test_chart_settings_reference_columns_in_the_sql():
    for card in SPEC.cards:
        for key in ("graph.dimensions", "graph.metrics"):
            for column in card.visualization_settings.get(key, []):
                assert re.search(rf"\b{column}\b", card.sql), f"{card.name}: {column}"


def test_cli_dry_run_lists_every_card_without_calling_anything():
    result = CliRunner().invoke(app, ["metabase-setup", "--dry-run"])
    assert result.exit_code == 0, result.output
    for card in SPEC.cards:
        assert card.name in result.output
