"""Generate tests/fixtures/mini_city_ml (deterministic).

Run: python tests/fixtures/make_mini_city_ml.py

A small synthetic city with a 140 day calendar, so the 90 day history plus 30 day label windows
fit. It contains one listing for every rule the feature builder applies:

    index 0  missing price, bedrooms and "Half-bath"
    index 1  "1.5 baths", superhost
    index 2  missing property type, instant_bookable and host_is_superhost
    index 3  missing accommodates                 -> dropped (missing accommodates)
    index 4  missing maximum_nights               -> dropped (missing maximum_nights)
    index 5  no calendar rows                     -> dropped (no calendar history)
    index 6  calendar days 0..99 only             -> dropped (incomplete label window)
    index 7  calendar days 100..139 only          -> dropped (no calendar history)
    index 8  calendar days 30..139 only           -> dropped (incomplete history window)

The calendar starts on 2026-09-25, so the earliest valid cutoff is 2026-12-24. One review of
listing index 10 is dated after that cutoff, and one review row is duplicated, to test the
review date filter and de-duplication. All text is synthetic.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

START = date(2026, 9, 25)
DAYS = 140
N_LISTINGS = 30
FIRST_ID = 5_000_001
OUT = Path(__file__).parent / "mini_city_ml"

NEIGHBOURHOODS = ["Altstadt-Lehel", "Schwabing-West", "Maxvorstadt", "Au-Haidhausen"]
ROOM_TYPES = ["Entire home/apt", "Private room", "Entire home/apt", "Hotel room"]
PROPERTY_TYPES = ["Entire rental unit", "Private room in rental unit", "Entire condo"]
BATHS = ["1 bath", "1.5 baths", "2 baths", "Half-bath", "1 shared bath", "Shared half-bath"]


def _listing_rows(rng: random.Random) -> list[dict]:
    rows = []
    for i in range(N_LISTINGS):
        rows.append(
            {
                "id": FIRST_ID + i,
                "host_id": 7000 + i % 18,
                "neighbourhood_cleansed": NEIGHBOURHOODS[i % 4],
                "latitude": round(48.10 + rng.random() * 0.1, 5),
                "longitude": round(11.50 + rng.random() * 0.1, 5),
                "property_type": PROPERTY_TYPES[i % 3],
                "room_type": ROOM_TYPES[i % 4],
                "accommodates": 1 + i % 5,
                "bedrooms": float(1 + i % 3),
                "beds": float(1 + i % 4),
                "bathrooms_text": BATHS[i % len(BATHS)],
                "price": f"${60 + 15 * i:,}.00",
                "minimum_nights": 1 + i % 4,
                "maximum_nights": 30 + 10 * i,
                "availability_30": rng.randint(0, 30),
                "availability_365": rng.randint(0, 365),
                "number_of_reviews": rng.randint(0, 80),
                "review_scores_rating": round(4 + rng.random(), 2),
                "instant_bookable": "t" if i % 3 == 0 else "f",
                "host_is_superhost": "t" if i % 4 == 0 else "f",
                "host_name": f"Host {i}",
            }
        )
    rows[0].update(price="", bedrooms="", bathrooms_text="Half-bath")
    rows[1].update(bathrooms_text="1.5 baths", host_is_superhost="t")
    rows[2].update(property_type="", instant_bookable="", host_is_superhost="")
    rows[3].update(accommodates="")
    rows[4].update(maximum_nights="")
    return rows


def _calendar_rows(rng: random.Random, listings: list[dict]) -> list[dict]:
    day_ranges = {5: range(0), 6: range(0, 100), 7: range(100, 140), 8: range(30, 140)}
    rows = []
    for i, listing in enumerate(listings):
        p_available = 0.05 + 0.9 * (i % 10) / 9
        for d in day_ranges.get(i, range(DAYS)):
            rows.append(
                {
                    "listing_id": listing["id"],
                    "date": (START + timedelta(days=d)).isoformat(),
                    "available": "t" if rng.random() < p_available else "f",
                    "minimum_nights": listing["minimum_nights"] or 1,
                    "maximum_nights": 30 + 10 * i if d % 7 else 365,
                }
            )
    return rows


def _review_rows(rng: random.Random, listings: list[dict]) -> list[dict]:
    rows = []
    review_id = 900_001
    for i, listing in enumerate(listings):
        if i < 9 or i % 4 == 0:
            continue
        for k in range(i % 5 + 1):
            when = START - timedelta(days=rng.randint(0, 900))
            comment = "" if (i + k) % 7 == 0 else "word " * rng.randint(1, 60)
            rows.append(
                {
                    "listing_id": listing["id"],
                    "id": review_id,
                    "date": when.isoformat(),
                    "reviewer_id": 31_000 + (i * 3 + k) % 17,
                    "reviewer_name": f"Guest {review_id}",
                    "comments": comment.strip(),
                }
            )
            review_id += 1
    ten = listings[10]["id"]
    rows.append(
        {"listing_id": ten, "id": review_id, "date": "2027-01-15", "reviewer_id": 31_999,
         "reviewer_name": "Guest future", "comments": "written after the cutoff " * 10}
    )
    rows.append(dict(rows[0]))
    return rows


def _write(name: str, rows: list[dict]) -> None:
    with open(OUT / name, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate() -> None:
    rng = random.Random(20260925)
    OUT.mkdir(parents=True, exist_ok=True)
    listings = _listing_rows(rng)
    _write("listings.csv", listings)
    _write("calendar.csv", _calendar_rows(rng, listings))
    _write("reviews.csv", _review_rows(rng, listings))


if __name__ == "__main__":
    generate()
    print(f"wrote {OUT}")
