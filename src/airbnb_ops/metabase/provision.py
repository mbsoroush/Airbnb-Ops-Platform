"""Idempotent provisioning: admin, warehouse connection, collection, cards, dashboard.

Safe to re-run. Existing objects are found by name and updated in place, so editing
dashboard.py and running again converges Metabase to the definition in code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .client import MetabaseClient
from .dashboard import GRID_WIDTH, CardSpec, DashboardSpec


@dataclass(frozen=True)
class WarehouseConnection:
    """How the Metabase server reaches Postgres (note: host is as seen from Metabase)."""

    name: str
    host: str
    port: int
    dbname: str
    user: str
    password: str

    def details(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password,
            "ssl": False,
        }


@dataclass(frozen=True)
class ProvisionResult:
    dashboard_id: int
    dashboard_url: str
    first_run: bool
    cards_created: int
    cards_updated: int


def card_payload(card: CardSpec, database_id: int, collection_id: int) -> dict[str, Any]:
    return {
        "name": card.name,
        "description": card.description or None,
        "type": "question",
        "display": card.display,
        "visualization_settings": card.visualization_settings,
        "collection_id": collection_id,
        "dataset_query": {
            "type": "native",
            "database": database_id,
            "native": {"query": card.sql},
        },
    }


def dashcard_payloads(spec: DashboardSpec, card_ids: dict[str, int]) -> list[dict[str, Any]]:
    """New dashcards get negative ids; the list replaces the dashboard's whole layout."""
    for card in spec.cards:
        if card.col < 0 or card.col + card.width > GRID_WIDTH:
            raise ValueError(f"Card {card.name!r} does not fit the {GRID_WIDTH}-column grid")
    return [
        {
            "id": -(index + 1),
            "card_id": card_ids[card.name],
            "row": card.row,
            "col": card.col,
            "size_x": card.width,
            "size_y": card.height,
        }
        for index, card in enumerate(spec.cards)
    ]


def _ensure_database(client: MetabaseClient, warehouse: WarehouseConnection) -> int:
    for database in client.list_databases():
        if database.get("name") == warehouse.name:
            return int(database["id"])
    database_id = client.create_database(warehouse.name, warehouse.details())
    client.sync_database(database_id)
    return database_id


def _ensure_collection(client: MetabaseClient, name: str, description: str) -> int:
    for collection in client.list_collections():
        if collection.get("name") == name and not collection.get("archived"):
            return int(collection["id"])
    return client.create_collection(name, description)


def provision(
    client: MetabaseClient,
    admin_email: str,
    admin_password: str,
    warehouse: WarehouseConnection,
    spec: DashboardSpec,
    site_name: str = "Airbnb Ops Platform",
    wait: bool = True,
) -> ProvisionResult:
    if wait:
        client.wait_until_healthy()
    first_run = client.authenticate(admin_email, admin_password, site_name)

    database_id = _ensure_database(client, warehouse)
    collection_id = _ensure_collection(client, spec.collection, spec.description)

    existing_cards = {
        item["name"]: int(item["id"]) for item in client.collection_items(collection_id, "card")
    }
    card_ids: dict[str, int] = {}
    created = updated = 0
    for card in spec.cards:
        payload = card_payload(card, database_id, collection_id)
        if card.name in existing_cards:
            card_ids[card.name] = existing_cards[card.name]
            client.update_card(card_ids[card.name], payload)
            updated += 1
        else:
            card_ids[card.name] = client.create_card(payload)
            created += 1

    existing_dashboards = {
        item["name"]: int(item["id"])
        for item in client.collection_items(collection_id, "dashboard")
    }
    dashboard_id = existing_dashboards.get(spec.name) or client.create_dashboard(
        spec.name, spec.description, collection_id
    )
    client.set_dashcards(dashboard_id, dashcard_payloads(spec, card_ids))

    return ProvisionResult(
        dashboard_id=dashboard_id,
        dashboard_url=f"{client.base_url}/dashboard/{dashboard_id}",
        first_run=first_run,
        cards_created=created,
        cards_updated=updated,
    )
