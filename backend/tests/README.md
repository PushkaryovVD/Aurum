# Backend tests

Integration tests use real PostgreSQL, **not the application's server**. The
shared fixture refuses to connect without explicit disposable-runtime metadata.
It validates the endpoint and the live server's `data_directory`, creates a
UUID-named `aurum_fixture_test_*` database with CREATE-only semantics, migrates
it, and drops only the exact OID/owner it created. Cleanup runs even if migration
setup fails; it never uses `FORCE` or terminates another process's connections.
The app's `lifespan` is not run and route DB dependencies are overridden.

## Running

Use a local, disposable PostgreSQL cluster owned by this test run. Do **not**
run tests inside the application container or against a deployment database.
Install `requirements-dev.txt` in a virtual environment and activate it first.
PostgreSQL server tools (`initdb`, `pg_ctl`, `pg_config`) must be installed.
From `backend/`:

```bash
PG_BIN="$(pg_config --bindir)"
RUNTIME="$(mktemp -d "${TMPDIR:-/tmp}/aurum-test-postgres-XXXXXX")"
export RUNTIME
export AURUM_POSTGRES_HOST=127.0.0.1 AURUM_POSTGRES_PORT=57613
export AURUM_POSTGRES_USER=postgres AURUM_POSTGRES_PASSWORD=''
export AURUM_DISPOSABLE_POSTGRES_RUNTIME="$RUNTIME/runtime.json"
"$PG_BIN/initdb" -D "$RUNTIME/data" -U postgres -A trust
"$PG_BIN/pg_ctl" -D "$RUNTIME/data" -l "$RUNTIME/server.log" \
  -o "-h 127.0.0.1 -p $AURUM_POSTGRES_PORT -k $RUNTIME" -w start
trap '"$PG_BIN/pg_ctl" -D "$RUNTIME/data" -m fast -w stop' EXIT
python - <<'PY'
import json, os
from pathlib import Path
workspace = Path(os.environ["RUNTIME"]).resolve()
(workspace / "runtime.json").write_text(json.dumps({
    "workspace": str(workspace), "data": str(workspace / "data"),
    "disposable": True, "host": os.environ["AURUM_POSTGRES_HOST"],
    "port": int(os.environ["AURUM_POSTGRES_PORT"]),
    "user": os.environ["AURUM_POSTGRES_USER"],
}))
PY
python -m pytest tests unit_tests -q -Werror -rs
```

Trust authentication is only for this disposable loopback cluster on an
isolated development/CI host. Pick another free port if needed; metadata and
`AURUM_POSTGRES_PORT` must agree. A preexisting database is never removed to
resolve a name collision. Metadata is an explicit opt-in, not a replacement
for provisioning a genuinely disposable cluster. Never point its `data` field
at application data. CI provisions the same local ownership contract and stops
its cluster in an `always()` cleanup step.

To run only fake-backed lifecycle safety checks (no PostgreSQL needed):

```bash
python -m pytest unit_tests/test_test_database_lifecycle.py -q -Werror
```

## Adding a test

- Use `client` (an `httpx.AsyncClient` wired to the app) to hit the API — prefer
  this over reaching into services/models directly to verify the contract.
- `account_id` and `categories` provide the fresh-install defaults.
- Every table is truncated and reseeded before each integration test (see
  `conftest.py::_clean_database`), so tests do not inherit earlier rows or IDs.
- Unit tests for refused destructive paths must use fakes, never real remote
  endpoints. Keep runtime metadata outside the repository.
