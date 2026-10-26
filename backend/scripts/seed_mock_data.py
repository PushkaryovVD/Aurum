"""Fills Aurum with a realistic demo dataset for local UI testing.

The data goes through the public REST API, exactly like the web app, so it
always matches the current schema: multi-currency fields, workspace scope,
categorization and validation are all applied by the server itself.

Run it against a running stack, for example from the backend container:

    docker compose exec backend python -m scripts.seed_mock_data --login you@example.com

or from your machine against the web port:

    python -m scripts.seed_mock_data --base-url http://localhost:3000 --login you@example.com

The password is read from AURUM_SEED_PASSWORD or asked interactively; it is
never stored. With accounts enabled the data is written into a separate
family space (default "Demo data", created when missing), so your real spaces
are never touched. Re-running replaces only what this script created before:
accounts named "Demo · …", their transactions and assets named "Demo · …".
In legacy auth-disabled mode the same prefix rule protects existing data.
"""
from __future__ import annotations

import argparse
import getpass
import os
import random
import sys
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

PREFIX = "Demo · "
MARKER = "[aurum-demo-seed]"
# Amounts below are written in "USD-sized" units and scaled per currency so
# the demo looks plausible whatever the account currency is.
CURRENCY_SCALE = {"KZT": Decimal("500"), "RUB": Decimal("90"), "UAH": Decimal("40")}


def _shift_month(d: date, months: int) -> date:
    index = d.month - 1 + months
    return date(d.year + index // 12, index % 12 + 1, 1)


class Seeder:
    def __init__(self, base_url: str, currency: str, months: int, seed: int) -> None:
        parts = urlsplit(base_url)
        self.origin = f"{parts.scheme}://{parts.netloc}"
        self.client = httpx.Client(base_url=f"{self.origin}/api", timeout=60, headers={"Origin": self.origin})
        self.currency = currency.upper()
        self.scale = CURRENCY_SCALE.get(self.currency, Decimal("1"))
        self.today = date.today()
        current = date(self.today.year, self.today.month, 1)
        self.month_starts = [_shift_month(current, -i) for i in range(months - 1, -1, -1)]
        self.random = random.Random(seed)

    # --- HTTP helpers -------------------------------------------------------
    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = self.client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise SystemExit(f"{method} {path} failed with {response.status_code}: {response.text[:300]}")
        return response

    def use_session(self, session: dict, workspace_id: str) -> None:
        self.client.headers["X-CSRF-Token"] = session["csrf_token"]
        self.client.headers["X-Aurum-Workspace"] = workspace_id

    # --- Authentication and target space ------------------------------------
    def sign_in_and_pick_space(self, login: str | None, password: str | None, space_name: str) -> str:
        status = self.request("GET", "/auth/status").json()
        if not status["app_auth_required"]:
            print("Accounts are disabled on this instance: writing into the legacy installation.")
            return "legacy installation"
        if not login or not password:
            raise SystemExit("This instance requires sign-in: pass --login and provide the password.")
        session = self.request("POST", "/auth/session", json={"identifier": login, "password": password}).json()
        space = next(
            (item for item in session["workspaces"] if item["display_name"] == space_name and item["kind"] == "household"),
            None,
        )
        if space is None:
            self.client.headers["X-CSRF-Token"] = session["csrf_token"]
            space = self.request("POST", "/workspaces", json={"display_name": space_name}).json()
            session = self.request("GET", "/auth/me").json()
        if space.get("role") not in {None, "owner", "editor"}:
            raise SystemExit(f"You cannot write into the '{space_name}' space.")
        self.use_session(session, space["id"])
        return space_name

    # --- Data ----------------------------------------------------------------
    def money(self, low: float, high: float) -> str:
        value = Decimal(str(round(self.random.uniform(low, high), 2))) * self.scale
        return str(value.quantize(Decimal("0.01")))

    def fixed(self, value: str) -> str:
        return str((Decimal(value) * self.scale).quantize(Decimal("0.01")))

    def day(self, month_start: date, day: int) -> date | None:
        try:
            value = date(month_start.year, month_start.month, day)
        except ValueError:
            return None
        return value if value <= self.today else None

    def wipe_previous_demo(self) -> None:
        accounts = self.request("GET", "/accounts", params={"include_archived": "true"}).json()
        demo_accounts = [item for item in accounts if item["name"].startswith(PREFIX)]
        for account in demo_accounts:
            while True:
                page = self.request(
                    "GET", "/transactions", params={"account_id": account["id"], "page_size": 200, "page": 1}
                ).json()
                if not page["items"]:
                    break
                for item in page["items"]:
                    self.request("DELETE", f"/transactions/{item['id']}")
        for asset in self.request("GET", "/assets").json():
            if asset["name"].startswith(PREFIX):
                self.request("DELETE", f"/assets/{asset['id']}")
        for account in demo_accounts:
            self.request("DELETE", f"/accounts/{account['id']}")

    def category_ids(self) -> dict[str, int]:
        wanted = {
            "Salary": "income", "Freelance": "income", "Housing & Utilities": "expense",
            "Groceries": "expense", "Dining Out": "expense", "Transportation": "expense",
            "Health & Fitness": "expense", "Entertainment": "expense", "Subscriptions": "expense",
            "Shopping": "expense",
        }
        existing = {item["name"]: item for item in self.request("GET", "/categories").json()}
        ids: dict[str, int] = {}
        for name, kind in wanted.items():
            item = existing.get(name)
            if item is None:
                item = self.request("POST", "/categories", json={"name": name, "kind": kind}).json()
            ids[name] = item["id"]
        return ids

    def create_account(self, name: str, kind: str, color: str) -> int:
        body = {"name": f"{PREFIX}{name}", "type": kind, "currency": self.currency, "color": color}
        return self.request("POST", "/accounts", json=body).json()["id"]

    def transactions(self, main: int, savings: int, card: int, categories: dict[str, int]) -> list[dict]:
        items: list[dict] = []

        def add(account: int, category: str | None, kind: str, value: str, text: str, when: date | None, **extra):
            if when is None:
                return
            items.append({
                "account_id": account,
                "category_id": categories[category] if category else None,
                "type": kind,
                "amount": value,
                "description": text,
                "date": when.isoformat(),
                "notes": MARKER,
                **extra,
            })

        for month in self.month_starts:
            add(main, "Salary", "income", self.money(8200, 8800), "Salary", self.day(month, 1))
            if month.month % 2 == 0:
                add(main, "Freelance", "income", self.money(500, 1500), "Freelance project", self.day(month, 15))
            add(main, "Housing & Utilities", "expense", self.money(2500, 2750), "Rent & utilities", self.day(month, 2))
            for day in (4, 11, 18, 25):
                add(main, "Groceries", "expense", self.money(45, 95), "Groceries", self.day(month, day))
            for day, text in [(3, "Restaurant"), (9, "Coffee shop"), (16, "Restaurant"), (23, "Takeout")]:
                add(main, "Dining Out", "expense", self.money(15, 70), text, self.day(month, day))
            for day in (5, 15, 25):
                add(main, "Transportation", "expense", self.money(35, 90), "Gas", self.day(month, day))
            add(main, "Health & Fitness", "expense", self.money(50, 90), "Gym membership", self.day(month, 6))
            add(main, "Entertainment", "expense", self.money(15, 55), "Movies", self.day(month, 22))
            for text, value in [("Netflix", "15.99"), ("Spotify", "10.99"), ("Cloud storage", "9.99")]:
                add(main, "Subscriptions", "expense", self.fixed(value), text, self.day(month, 1))
            add(card, "Shopping", "expense", self.money(60, 220), "Online shopping", self.day(month, 20))
            add(card, "Dining Out", "expense", self.money(20, 60), "Dinner out", self.day(month, 10))
            transfer = self.money(800, 1500)
            # Same-currency transfer: the destination receives exactly the amount sent.
            add(main, None, "transfer", transfer, "Move to savings", self.day(month, 27),
                transfer_account_id=savings, transfer_amount=transfer)
        return items

    def assets(self) -> None:
        first, last = self.month_starts[0], self.today
        plans = [
            ("Brokerage account", "investments", ["380000", "392000", "405000", "415000", "428500"]),
            ("Bitcoin", "crypto", ["3000", "3800", "3200", "4100", "3900"]),
            ("Apartment", "real_estate", ["345000", "348000", "350000"]),
            ("Car", "vehicles", ["24000", "23200", "22500"]),
            ("Gold coins", "other", ["1500", "2000"]),
        ]
        for name, asset_class, values in plans:
            dates = [self.month_starts[min(i, len(self.month_starts) - 1)] for i in range(len(values))]
            dates[-1] = last
            created = self.request("POST", "/assets", json={
                "name": f"{PREFIX}{name}",
                "asset_class": asset_class,
                "currency": self.currency,
                "value": self.fixed(values[0]),
                "as_of_date": max(dates[0], first).isoformat(),
                "notes": MARKER,
            }).json()
            seen = {dates[0]}
            for when, value in zip(dates[1:], values[1:]):
                if when in seen:
                    continue
                seen.add(when)
                self.request("POST", f"/assets/{created['id']}/valuations", json={
                    "value": self.fixed(value),
                    "as_of_date": when.isoformat(),
                })


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--base-url", default=os.environ.get("AURUM_SEED_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--login", default=os.environ.get("AURUM_SEED_LOGIN"))
    parser.add_argument("--space", default="Demo data", help="family space to fill (created when missing)")
    parser.add_argument("--currency", default="KZT", help="currency of the demo accounts and assets")
    parser.add_argument("--months", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42, help="random seed for a reproducible dataset")
    args = parser.parse_args(argv)

    seeder = Seeder(args.base_url, args.currency, max(1, args.months), args.seed)
    password = os.environ.get("AURUM_SEED_PASSWORD")
    status = seeder.request("GET", "/auth/status").json()
    if status["app_auth_required"] and not password:
        password = getpass.getpass(f"Aurum password for {args.login}: ")
    target = seeder.sign_in_and_pick_space(args.login, password, args.space)

    print(f"Replacing previous demo data in {target}...")
    seeder.wipe_previous_demo()
    categories = seeder.category_ids()
    main_id = seeder.create_account("Main account", "checking", "#2a78d6")
    savings_id = seeder.create_account("Savings", "savings", "#1baf7a")
    card_id = seeder.create_account("Credit card", "credit_card", "#e34948")
    items = seeder.transactions(main_id, savings_id, card_id, categories)
    print(f"Creating {len(items)} transactions over {len(seeder.month_starts)} months...")
    seeder.request("POST", "/transactions/bulk", json={"items": items})
    print("Creating assets and valuation history...")
    seeder.assets()
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
