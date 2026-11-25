"""Provisioning flow against a stateful in-memory fake of the Metabase API."""
import json
import re
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

import pytest

from airbnb_ops.metabase.client import MetabaseClient, MetabaseError
from airbnb_ops.metabase.dashboard import GRID_WIDTH, default_dashboard
from airbnb_ops.metabase.provision import WarehouseConnection, provision

EMAIL, PASSWORD = "admin@example.com", "a-long-random-admin-password"
WAREHOUSE = WarehouseConnection(
    name="Airbnb Warehouse", host="postgres", port=5432, dbname="airbnb",
    user="metabase_reader", password="reader-secret",
)
BASE = "http://metabase.test"


class FakeMetabase:
    """Just enough of the Metabase API to run provisioning end to end, with real state."""

    def __init__(self) -> None:
        self.setup_token: str | None = "setup-token-123"
        self.admin: tuple[str, str] | None = None
        self.calls: list[tuple[str, str, object]] = []
        self.databases: list[dict] = []
        self.collections: list[dict] = []
        self.cards: dict[int, dict] = {}
        self.dashboards: dict[int, dict] = {}
        self.health_failures = 0
        self._ids = 0

    def _next(self) -> int:
        self._ids += 1
        return self._ids

    def count(self, method: str, pattern: str) -> int:
        return sum(1 for m, p, _ in self.calls if m == method and re.fullmatch(pattern, p))

    def __call__(self, method, url, headers, data, timeout):
        parsed = urlparse(url)
        body = json.loads(data) if data else None
        self.calls.append((method, parsed.path, body))
        status, payload = self._route(method, parsed.path, parse_qs(parsed.query), body, headers)
        return status, json.dumps(payload).encode()

    def _route(self, method, path, query, body, headers):
        if (method, path) == ("GET", "/api/health"):
            if self.health_failures > 0:
                self.health_failures -= 1
                raise ConnectionRefusedError("connection refused")
            return 200, {"status": "ok"}
        if (method, path) == ("GET", "/api/session/properties"):
            return 200, {"setup-token": self.setup_token}
        if (method, path) == ("POST", "/api/setup"):
            if not self.setup_token or body.get("token") != self.setup_token:
                return 403, {"message": "bad token"}
            self.admin = (body["user"]["email"], body["user"]["password"])
            self.setup_token = None
            return 200, {"id": "session-setup"}
        if (method, path) == ("POST", "/api/session"):
            if self.admin == (body["username"], body["password"]):
                return 200, {"id": "session-login"}
            return 401, {"errors": {"password": "did not match stored password"}}
        if headers.get("X-Metabase-Session") not in {"session-setup", "session-login"}:
            return 401, {"message": "Unauthenticated"}

        if (method, path) == ("GET", "/api/database"):
            return 200, {"data": self.databases, "total": len(self.databases)}
        if (method, path) == ("POST", "/api/database"):
            database = {"id": self._next(), "name": body["name"], "engine": body["engine"],
                        "details": body["details"]}
            self.databases.append(database)
            return 200, database
        if method == "POST" and re.fullmatch(r"/api/database/\d+/sync_schema", path):
            return 200, {"status": "ok"}
        if (method, path) == ("GET", "/api/collection"):
            return 200, [{"id": "root", "name": "Our analytics"}, *self.collections]
        if (method, path) == ("POST", "/api/collection"):
            collection = {"id": self._next(), "name": body["name"], "archived": False}
            self.collections.append(collection)
            return 200, collection
        match = re.fullmatch(r"/api/collection/(\d+)/items", path)
        if method == "GET" and match:
            store = self.cards if query["models"] == ["card"] else self.dashboards
            items = [
                {"id": item_id, "name": item["name"], "model": query["models"][0]}
                for item_id, item in store.items()
                if item.get("collection_id") == int(match[1])
            ]
            return 200, {"data": items, "total": len(items)}
        if (method, path) == ("POST", "/api/card"):
            card = {**body, "id": self._next()}
            self.cards[card["id"]] = card
            return 200, card
        match = re.fullmatch(r"/api/card/(\d+)", path)
        if method == "PUT" and match:
            self.cards[int(match[1])].update(body)
            return 200, self.cards[int(match[1])]
        if (method, path) == ("POST", "/api/dashboard"):
            dashboard = {**body, "id": self._next(), "dashcards": []}
            self.dashboards[dashboard["id"]] = dashboard
            return 200, dashboard
        match = re.fullmatch(r"/api/dashboard/(\d+)", path)
        if method == "PUT" and match:
            self.dashboards[int(match[1])]["dashcards"] = body["dashcards"]
            return 200, self.dashboards[int(match[1])]
        return 404, {"message": f"no route for {method} {path}"}


@pytest.fixture()
def fake() -> FakeMetabase:
    return FakeMetabase()


@pytest.fixture()
def client(fake) -> MetabaseClient:
    return MetabaseClient(BASE, transport=fake, sleep=lambda _seconds: None)


def run(client, spec=None, password=PASSWORD):
    return provision(client, EMAIL, password, WAREHOUSE, spec or default_dashboard())


def test_first_run_provisions_everything(fake, client):
    spec = default_dashboard()
    result = run(client, spec)

    assert result.first_run and result.cards_created == len(spec.cards) == len(fake.cards)
    assert result.cards_updated == 0

    # first-time setup used the one-time token and the nested user/prefs shape
    setup = next(body for method, path, body in fake.calls if path == "/api/setup")
    assert setup["token"] == "setup-token-123"
    assert setup["user"]["email"] == EMAIL and setup["user"]["password"] == PASSWORD
    assert setup["prefs"]["site_name"]

    # warehouse connection uses the reader credentials and the host as seen from Metabase
    (database,) = fake.databases
    assert database["engine"] == "postgres"
    assert database["details"] == {
        "host": "postgres", "port": 5432, "dbname": "airbnb",
        "user": "metabase_reader", "password": "reader-secret", "ssl": False,
    }

    # one collection, every card is a native query in that collection against that database
    (collection,) = fake.collections
    for card in fake.cards.values():
        assert card["type"] == "question" and card["collection_id"] == collection["id"]
        assert card["dataset_query"]["type"] == "native"
        assert card["dataset_query"]["database"] == database["id"]
    assert {c["dataset_query"]["native"]["query"] for c in fake.cards.values()} == {
        c.sql for c in spec.cards
    }

    # dashboard layout: new dashcards use unique negative ids, valid grid, one per card
    (dashboard,) = fake.dashboards.values()
    dashcards = dashboard["dashcards"]
    assert {d["card_id"] for d in dashcards} == set(fake.cards)
    ids = [d["id"] for d in dashcards]
    assert len(set(ids)) == len(ids) and all(i < 0 for i in ids)
    assert all(d["col"] + d["size_x"] <= GRID_WIDTH for d in dashcards)
    assert result.dashboard_url == f"{BASE}/dashboard/{dashboard['id']}"

    # every request after login carried the session header (checked by the fake's 401)
    assert fake.count("GET", "/api/health") == 1


def test_rerun_is_idempotent_and_applies_edits(fake, client):
    spec = default_dashboard()
    run(client, spec)

    edited = replace(spec, cards=(replace(spec.cards[1], sql="SELECT 1"), *spec.cards[2:],
                                  spec.cards[0]))
    result = run(client, edited)

    assert not result.first_run
    assert result.cards_created == 0 and result.cards_updated == len(edited.cards)
    assert fake.count("POST", "/api/database") == 1
    assert fake.count("POST", "/api/collection") == 1
    assert fake.count("POST", "/api/card") == len(spec.cards)
    assert fake.count("POST", "/api/dashboard") == 1
    assert len(fake.cards) == len(spec.cards) and len(fake.dashboards) == 1

    updated = next(c for c in fake.cards.values() if c["name"] == spec.cards[1].name)
    assert updated["dataset_query"]["native"]["query"] == "SELECT 1"
    (dashboard,) = fake.dashboards.values()
    assert len(dashboard["dashcards"]) == len(edited.cards)


def test_wrong_admin_password_on_existing_instance_explains_itself(fake, client):
    run(client)
    with pytest.raises(MetabaseError, match="already set up") as excinfo:
        run(client, password="not-the-password")
    assert excinfo.value.status == 401


def test_wait_until_healthy_retries_then_succeeds(fake):
    fake.health_failures = 2
    sleeps: list[float] = []
    MetabaseClient(BASE, transport=fake, sleep=sleeps.append).wait_until_healthy(
        timeout=60, interval=1
    )
    assert sleeps == [1, 1]


def test_wait_until_healthy_times_out_with_reason(fake):
    fake.health_failures = 10**6
    client = MetabaseClient(BASE, transport=fake, sleep=lambda _seconds: None)
    with pytest.raises(TimeoutError, match="connection refused"):
        client.wait_until_healthy(timeout=0, interval=0)


def test_api_errors_carry_status_and_body(client):
    client.authenticate(EMAIL, PASSWORD, "Test site")
    with pytest.raises(MetabaseError, match="404") as excinfo:
        client._request("GET", "/api/nope")
    assert "no route" in excinfo.value.detail


def test_requests_without_login_are_rejected(client):
    with pytest.raises(MetabaseError) as excinfo:
        client.list_databases()
    assert excinfo.value.status == 401


def test_only_http_urls_are_accepted():
    with pytest.raises(ValueError, match="http"):
        MetabaseClient("file:///etc/passwd")
