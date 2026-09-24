# Envelope / zero-based budgeting — architecture and delivery contract

Design gate for PLAN.md milestone **`feature/envelope-budgeting`** (PLAN.md:300-311).

Status: **implementation-ready**. This document is the contract for the backend,
frontend, backup/restore and QA workers. Decisions in this document are final
unless the design is amended on the record; workers must not re-decide them
locally (see §11 for the two questions deliberately left open).

Grounding: written against `develop` at `e477d62` in the task worktree
`.worktrees/t_7921a302`, with `alembic` head verified as **`b7e2c4f19a35`**
(`add_categorization_rules`; no other revision lists it as `down_revision`).

---

## 1. Scope and non-goals

In scope (PLAN.md:302-311):

- monthly income-to-envelope allocations with `planned`, `activity`, `available`
  and configurable positive/negative rollover;
- enforcement that allocations for a month cannot exceed *money available to
  assign*;
- envelope-to-envelope moves that create no income and no expense;
- reuse of the category hierarchy, with envelope balances held **separate** from
  `accounts.balance` and from the legacy `budgets` table;
- templates, next-month funding, overspending warnings, immutable audit log;
- accepted edge cases: late income, refunds, split transactions, category moves,
  rollover, editing an operation in a closed month;
- FastAPI + SQLAlchemy + Alembic backend, React/TS UI, RU/EN, mobile-first,
  backward-compatible JSON backup/restore.

Non-goals (do not implement, do not "improve while here"):

- changing, migrating or deleting the legacy `/budgets` model, service, routes
  or `BudgetPage`; both models coexist. The only hard requirement is that
  envelope math never reads or writes `budgets`, and legacy tests keep passing;
- account scoping of envelopes (envelopes are global by category, across all
  accounts and currencies);
- scheduled/automatic posting, bank sync, or envelope-level recurrence;
- envelope-aware reporting pages beyond a single insights alert (§7.8);
- moving `bin/`-level precision scales; see the precision note in §3.1.

---

## 2. Current-state inventory

### 2.1 What exists today

| Concern | File | Shape |
|---|---|---|
| Legacy limit budget | `backend/app/models/budget.py` | `budgets(id, category_id UNIQUE FK->categories ON DELETE CASCADE, monthly_limit Numeric(14,2))` + `TimestampMixin` |
| Legacy budget API | `backend/app/api/routes/budgets.py` | `GET /budgets`, `GET /budgets/status?year&month`, `POST`, `PATCH /{id}`, `DELETE /{id}` |
| Legacy budget logic | `backend/app/services/budget_service.py` | month bounds; parent category rolls children up (`coalesce(parent_id, id)` convention); plain + split sums; `spent/remaining/percent/is_over_budget` |
| Categories | `backend/app/models/category.py` | `categories(id, name, kind, icon, color, sort_order, is_default, parent_id)` — hierarchy is **one level deep only**, enforced in `routes/categories.py` |
| Ledger | `backend/app/models/transaction.py` | `transactions(..., type, amount Numeric(14,2), currency, transaction_amount Numeric(14,2), exchange_rate_to_kzt Numeric(20,10), base_amount_kzt Numeric(18,2), category_id FK->categories ON DELETE SET NULL, date, purpose)`; `transaction_splits(id, transaction_id, category_id NULL, amount Numeric(14,2))` — a split parent has `category_id = NULL` |
| Reporting-currency helper | `backend/app/services/currency.py` | `transaction_amount_kzt()` = `base_amount_kzt` else `amount` when account currency is KZT else **NULL**; `split_amount_kzt()` analogous |
| Insights alerts | `backend/app/services/insights_service.py` | `budget_exceeded` alert built from `get_budget_status(today)`; alert `key` + `params`, rendered by `frontend/src/components/insights/AlertBanner.tsx` |
| Backup | `backend/app/schemas/backup.py`, `backend/app/services/backup_service.py` | `BackupPayload.aurum_backup_version` (value 2) + per-table `*Backup` models; every post-v2 table is an **optional list defaulting to `[]`** so an older file imports; `restore_backup()` deletes every table, inserts, then `_reset_sequence()` |
| Tests | `backend/tests/conftest.py`, `backend/tests/helpers.py` | real Postgres `aurum_test`, created fresh and migrated with the real Alembic chain per session; `money()` / `txn_payload()` helpers; seeded default categories/account/settings |

### 2.2 Prior partial attempt (reference only)

`.worktrees/t_b02bdcb0` holds an **uncommitted** partial implementation
(`models/envelope.py`, `schemas/envelope.py`, `services/envelope_service.py`,
`routes/envelopes.py`, `alembic/versions/d9e4f6a7b821_add_envelope_budgeting.py`,
`tests/test_envelopes.py`, plus correct-looking backup wiring in
`schemas/backup.py` / `services/backup_service.py` / `alembic/env.py` /
`main.py` / `models/__init__.py`).

It is **not** the contract and must not be merged blindly. Verified defects:

1. `_allocations_for_month()` and `get_status()` issue per-category correlated
   subqueries inside a loop → SQLAlchemy `cartesian product` warnings and N+1;
2. rollover chain is only one month deep and only for categories that had a row
   last month → a gap month breaks carryover, and the milestone test
   `test_envelope_tracks_split_spending_refunds_and_rollover` fails
   (`September items` empty, `IndexError` on `september["items"][0]`);
3. the rollover **policy** is read from the *current* month's row instead of the
   outgoing month's (§4.5);
4. `available_to_assign` uses only the current month's income, so it is not
   zero-based and cannot express next-month funding (§4.3);
5. activity ignores refunds entirely despite the test comment claiming they are
   handled (the test posts `category_id=None`, so it asserts nothing);
6. `planned_amount` and `assigned_amount` semantics are conflated
   (`planned or assigned`), templates cannot set a plan without moving money,
   and `apply_template` assigns `0` while calling itself "apply";
7. there is no month row, so "closed month" is unimplementable and closure
   state/drift cannot be persisted or backed up.

Reuse from it: the backup/restore wiring shape in `schemas/backup.py`,
`services/backup_service.py`, `models/__init__.py`, `alembic/env.py` and
`main.py` is correct and should be reproduced (with the additions in §6).

---

## 3. Data model

Five new tables in `backend/app/models/envelope.py`. All money columns are
`Numeric(14, 2)`, matching `budgets.monthly_limit` and `transactions.amount`.

### 3.1 `envelope_months`

```
id                    Integer PK
year                  Integer NOT NULL, CHECK 2000..2100
month                 Integer NOT NULL, CHECK 1..12
is_closed             Boolean NOT NULL default false
closed_at             DateTime(timezone=True) NULL
closed_activity_total Numeric(14,2) NULL   -- sum of all envelope activity at close time
created_at / updated_at via TimestampMixin
UNIQUE (year, month)
```

`closed_activity_total` exists solely for closed-month drift detection (§4.7);
it is `NULL` while open. The row is also the **tracking-start marker**: the
earliest `envelope_months` row defines where cumulative carryover begins (§4.3).

Precision note: `Numeric(14,2)` follows the current `budgets`/`transactions`
convention. When `feature/financial-precision` lands its end-to-end scale
decision, envelope money columns move with it; that is recorded in TODO.md, not
done here.

### 3.2 `envelope_allocations`

```
id                Integer PK
year, month       Integer NOT NULL
category_id       Integer NOT NULL FK->categories(id) ON DELETE CASCADE
assigned_amount   Numeric(14,2) NOT NULL default 0, CHECK >= 0
planned_amount    Numeric(14,2) NOT NULL default 0, CHECK >= 0
rollover_positive Boolean NOT NULL default true
rollover_negative Boolean NOT NULL default true
created_at / updated_at via TimestampMixin
UNIQUE (year, month, category_id)
INDEX (year, month)
```

`assigned_amount` is the money-moving number. `planned_amount` is an advisory
target only — it constrains nothing and moves nothing. A category may have at
most one envelope per month; there is no separate "envelope" entity — the
category *is* the envelope, exactly as PLAN.md:306 requires ("reuse the category
hierarchy").

`kind` restriction: only `CategoryKind.EXPENSE` categories can hold an envelope.
Enforced in the service (400), not at the DB level, matching
`create_budget()`'s existing behaviour.

### 3.3 `envelope_audit_logs` (append-only)

```
id               Integer PK
year, month      Integer NOT NULL
event_type       String(24) NOT NULL   -- see §4.8 for the closed set
category_id      Integer NULL FK->categories(id) ON DELETE SET NULL
from_category_id Integer NULL FK->categories(id) ON DELETE SET NULL
to_category_id   Integer NULL FK->categories(id) ON DELETE SET NULL
amount           Numeric(14,2) NOT NULL  -- signed delta, semantics per event_type
note             Text NULL
created_at       DateTime(timezone=True) NOT NULL server_default=now()
INDEX (year, month)
```

`from_/to_category_id` are `SET NULL` and `category_id` is `SET NULL`: deleting a
category must not destroy the audit trail, only its category references
(`envelope_allocations` itself cascades — losing the plan is acceptable, losing
history is not). Application code never issues `UPDATE`/`DELETE` against this
table except during `restore_backup()` (§6.3).

### 3.4 `envelope_templates`, 3.5 `envelope_template_items`

```
envelope_templates(id PK, name String(100) NOT NULL UNIQUE)

envelope_template_items(
  id PK,
  template_id FK->envelope_templates(id) ON DELETE CASCADE NOT NULL,
  category_id FK->categories(id) ON DELETE CASCADE NOT NULL,
  planned_amount Numeric(14,2) NOT NULL CHECK >= 0,
  rollover_positive Boolean NOT NULL default true,
  rollover_negative Boolean NOT NULL default true,
  UNIQUE (template_id, category_id)
)
```

A template carries **plan only** — no assigned amounts. Applying it cannot move
money (§4.6).

### 3.6 Invariants (assert these in tests)

- **INV-1** `Σ assigned_amount` for a month never exceeds that month's money
  available to assign (enforced at write time, §4.4).
- **INV-2** No envelope operation writes `transactions`, `transaction_splits`,
  `accounts.balance`, or `budgets`. Account balances are byte-identical before
  and after any envelope action.
- **INV-3** An envelope-to-envelope move changes no income and no expense total
  for the month; `Σ assigned_amount` across the month is unchanged.
- **INV-4** `envelope_months.year/month` is the single source of truth for the
  tracking boundary and for closure.
- **INV-5** `envelope_audit_logs` rows are never mutated or deleted by
  application code.

---

## 4. Semantics and calculation rules

All envelope arithmetic is in the **reporting currency (KZT)**, using the same
`transaction_amount_kzt()` / `split_amount_kzt()` expressions the budgets and
reports already use. Envelope figures are therefore comparable across accounts
and currencies, and are never a currency-conversion of an account balance.

### 4.1 Query shape (fixes the prior N+1/cartesian defect)

`get_month(year, month)` must run a **fixed, small number of aggregate queries**
and fold in Python. No per-category query inside a loop. Required queries:

1. all `envelope_allocations` rows with `(year, month) <= (year, month)` of the
   request, for the whole tracking window → `{month: {category_id: row}}`;
2. all `envelope_months` rows;
3. monthly income: `SELECT date_trunc('month', t.date), sum(transaction_amount_kzt())`
   for `t.type = INCOME` and `(t.category_id IS NULL OR c.kind = 'income')`,
   joined to `accounts` and outer-joined to `categories`, grouped by month;
4. monthly expense activity by resolved category: one grouped query over
   `transactions` (plain rows, `category_id` set) **union** one grouped query
   over `transaction_splits` (their parent's date, `type = EXPENSE`), each
   grouped by `(month, category_id)` and converted with the KZT helper;
5. monthly refunds: as (3) but `type = INCOME AND c.kind = 'expense'`, grouped by
   `(month, resolved category_id)`.

Then fold months ascending §4.4. Total: 5 statements regardless of month count.
Telemetry-free and testable; the SQLAlchemy `cartesian product` warning must be
absent from the test run (explicit acceptance item).

Rows whose KZT value resolves to `NULL` (non-KZT account without
`base_amount_kzt` — see `currency.py`) are **excluded and reported**, never
treated as zero: the month response sets `fx_incomplete: true` and emits warning
`fx_coverage_incomplete` (§4.7). This mirrors the PLAN.md:96-97 multicurrency
rule ("never silently add unresolved currencies").

### 4.2 Definitions

For envelope `C` in month `M`:

```
activity(M, C)      = refunds(M, C) - spending(M, C)      -- spending positive, refunds positive
carried_in(M, C)    = rollover_out(M-1, C)                -- §4.5
available(M, C)     = carried_in(M, C) + assigned(M, C) + activity(M, C)
is_overspent(M, C)  = available(M, C) < 0
```

`activity` is **negative when money leaves the envelope**, so a plain
`available = Σ` reads correctly. `refunds` and `spending` are both non-negative.

Month-level:

```
income(M)              = Σ KZT of qualifying INCOME transactions dated in M        (§4.3)
unassigned(M)          = income(M) + refunds_stray(M) - assigned(M)
available_to_assign(M) = Σ over tracking window of unassigned(m), m <= M          (§4.3)
```

### 4.3 Income vs. refund, and money available to assign

Classification of an `INCOME` transaction is deterministic and total:

- `category_id IS NULL`, or the category's `kind == INCOME` → **income**. Counts
  into `income(M)`. This includes investment cash legs (dividends, coupons,
  fees credits): they are real money and stay assignable, consistent with
  PLAN.md:179.
- category's `kind == EXPENSE` and an envelope exists for that category (or its
  parent, §4.4) in `M` → **refund**. Increases `activity` of that envelope. It
  does **not** also count as income (that would double-count).
- category's `kind == EXPENSE` and no envelope exists in `M` → **stray refund**.
  It counts toward `unassigned(M)` (the money is real and must not vanish) and
  raises the informational warning `refund_without_envelope`.

**Money available to assign is cumulative**, not per-month:

```
available_to_assign(M) = Σ_{m in [start, M]} ( income(m) + refunds_stray(m) - assigned(m) )
```

where `start` is the earliest `envelope_months` row (§3.1). Rationale: this is
what makes the milestone's listed behaviours fall out of one rule instead of
special cases —

- **late income**: income recorded in `M` after allocations were made simply
  raises `available_to_assign(M)` on the next read; already-valid allocations
  are never retro-invalidated (INV-1 is checked against the delta at write time,
  §4.4);
- **next-month funding**: money received in `M` and left unassigned carries into
  `M+1` automatically as part of the running sum, so funding next month needs no
  separate money bucket;
- **over-assignment after income is deleted**: a deleted/edited income row can
  drive `available_to_assign(M)` negative. This is allowed (the ledger is the
  truth) and surfaced as warning `available_to_assign_negative` with the amount
  — never blocked, never auto-unassigned.

`start` is created explicitly: `POST /envelopes/{year}/{month}/open` creates the
`envelope_months` row, and the first allocation write also creates it
(implicitly). Income dated **before** `start` is out of the window and raises the
informational warning `income_before_tracking_start` (amount + earliest such
date) so the UI can explain why it is not assignable. `GET /envelopes/{y}/{m}`
returns `tracking_start: {year, month} | null`.

### 4.4 Activity attribution, rollup, splits and category moves

Hierarchy is one level deep, so attribution is:

`spending(M, C)` = KZT of `EXPENSE` rows dated in `M` whose category is `C`,
**plus** for a top-level `C`, the rows of its direct children that have **no
envelope row of their own in `M`**. Symmetrically for refunds.

A transaction is counted **exactly once**. A child that has its own envelope in
`M` is excluded from the parent's activity, so funding parent and child never
double-funds the same receipt. This deliberately differs from the legacy
`budgets` rollup, which *displays* a child's spend in both bars; budgets are
display-only limits, envelopes are money, so double counting is not acceptable
there. Document the difference in DOCS.md.

- **Split transactions**: a split parent has `category_id = NULL`; its lines live
  in `transaction_splits`. Activity for `C` adds the split lines whose
  `category_id` is `C` (or an unattributed child of `C`, per the rule above),
  converted with `split_amount_kzt()`. The parent row itself contributes nothing.
  Both halves are summed per §4.1 queries (4).
- **Category moves** ("recategorising" an existing transaction, `PATCH
  /transactions/{id}` with a new `category_id`): no envelope code runs. The next
  read recomputes activity from the new category, so money visibly leaves one
  envelope and enters another. This is correct and is an acceptance case. If the
  month is closed, §4.7 drift applies.
- **Transfers** (`type = TRANSFER`) and `EXPENSE`/`INCOME` rows with
  `purpose` set never cross the envelope boundary in a special way: only
  `type = EXPENSE` contributes spending and only `type = INCOME` contributes
  income or refunds. A transfer between own accounts is therefore envelope-neutral
  (INV-3).
- **Tombstoned categories**: `category_id` is `SET NULL` on delete, so deleting a
  category makes its historical rows uncategorised — they leave every envelope's
  activity and become invisible to envelopes (same as budgets today). Acceptable,
  and noted in TODO.md.

### 4.5 Rollover

Two independent booleans per envelope row: `rollover_positive` (carry a positive
leftover forward) and `rollover_negative` (carry an overspend forward). Defaults
`true`/`true`.

```
rollover_out(M, C) = available(M, C)  if (available(M, C) > 0 and row(M,C).rollover_positive)
                                       or (available(M, C) < 0 and row(M,C).rollover_negative)
                   = 0                otherwise, and always 0 when no row(M, C) exists
```

The policy read is the **outgoing month's** row (`M`), because that row owns
month `M`'s funds and its flag is what the user set while looking at `M`. This is
the corrected semantics versus the prior attempt (§2.2 defect 3).

- Rollover is a **chain**, not one hop: month `M`'s `carried_in` is month `M-1`'s
  `rollover_out`, which itself depends on `M-2`, back to `start`. It is computed
  by the ascending fold of §4.1, so multi-month chains and **gap months** work:
  a month with no envelope row for `C` has `assigned = planned = 0` and still
  carries `C`'s activity and any incoming carry, but **rolls nothing out**
  (no row ⇒ no policy ⇒ `rollover_out = 0`). Document this explicitly: an
  untouched gap month is a hard reset for that category. (Open question 1, §11,
  is whether to change this.)
- A category with non-zero `activity` or non-zero `carried_in` in `M` but **no
  row** still appears in `items` with `assigned_amount = planned_amount = 0` and
  `is_unbudgeted = true` — unbudgeted spending must be visible, never hidden.
- Rollover values are snapshots: they may be edited until the month is closed
  (§4.7). Editing `M-1`'s flags changes `M`'s `carried_in` retroactively; the UI
  must recompute/invalidate both months.

### 4.6 Templates, funding, next-month funding

Three separate operations, deliberately not conflated (fixes §2.2 defect 6):

- **Apply template** — `POST /envelopes/{y}/{m}/apply-template/{template_id}`:
  upserts a row per template item with `planned_amount` and the rollover flags
  from the item, keeping the existing `assigned_amount`. **Moves no money.**
  Audited as `template_applied` (amount = Σ planned written, note = template
  name). Idempotent.
- **Fund** — `POST /envelopes/{y}/{m}/fund` with body
  `{template_id?: int|null, copy_plan_from?: {year, month}|null}`: for each
  target category in a deterministic order (template item order, else
  `categories.sort_order, id`), assign
  `delta = min(max(planned - assigned, 0), remaining_available)` walking down
  until `remaining_available` is exhausted. Because `delta` is clamped to the
  remaining available, INV-1 cannot be violated and funding never fails for lack
  of money — it reports what it could not fund. Returns the month status plus
  `unfunded: [{category_id, shortfall}]`. One audit row per category actually
  funded (`event_type = allocation`, `amount = delta`), committed atomically
  with the assignments. `copy_plan_from`, when given, is applied first exactly
  like `apply-template` for the categories that have no `planned_amount` yet in
  the target month.
- **Fund next month** — `POST /envelopes/{y}/{m}/fund-next-month`: a thin,
  explicit alias for `fund(y, m+1)` with `copy_plan_from = {y, m}`. It exists as
  a named endpoint because PLAN.md:308 lists next-month funding as a feature and
  the UI needs a stable call; it adds no new money semantics.

Templates CRUD: `GET /envelopes/templates`, `POST /envelopes/templates`
(body `{name, items: [{category_id, planned_amount, rollover_positive,
rollover_negative}]}`), `PATCH /envelopes/templates/{id}` (replace items),
`DELETE /envelopes/templates/{id}`. Only expense categories are accepted; an
unknown/income category is 400. Deleting a template never touches allocations.

### 4.7 Closed months

`POST /envelopes/{y}/{m}/close` sets `is_closed = true`, `closed_at = now()` and
`closed_activity_total = Σ activity(m, C)` over all envelopes of `m`.
`POST /envelopes/{y}/{m}/reopen` clears all three and is audited.

- While closed, **envelope planning writes are rejected with 409**: allocation
  PUT/DELETE, moves, apply-template, fund, fund-next-month. `open` on an existing
  month is idempotent.
- The **ledger is not locked**. A transaction created, edited, re-dated into, or
  deleted from a closed month's range is allowed — envelopes do not own the
  ledger. Instead the month response reports
  `has_ledger_drift: true` when `Σ activity(m, ·) != closed_activity_total`, plus
  warning `closed_month_ledger_drift` carrying both totals and the delta. The
  envelope view of a closed month is therefore always truthful, and the change is
  never silent. Reopening and re-closing refreshes the snapshot.
- This is the whole "editing an operation in a closed month" behaviour: allowed,
  detected, labelled. No transaction route needs to know envelopes exist, which
  keeps the modules decoupled (CLAUDE.md:2).

### 4.8 Audit events (closed set)

| `event_type` | `amount` | fields set | when |
|---|---|---|---|
| `allocation` | signed delta to `assigned_amount` | `category_id` | allocation put / delete / fund |
| `move` | positive transferred amount | `from_category_id`, `to_category_id`, `note` | move |
| `template_applied` | Σ planned written | `note` = template name | apply-template / fund's copy-plan step |
| `month_closed` | `closed_activity_total` (may be negative) | — | close |
| `month_reopened` | 0 | — | reopen |

`plan_updated` is **not** a separate event: a `planned_amount`-only change emits
`allocation` with `amount = 0`. This keeps the set small and every money movement
auditable.

Immutability enforcement (INV-5): SQLAlchemy `before_update` and `before_delete`
mapper events on `EnvelopeAuditLog` raise `RuntimeError`, plus there are no
PATCH/DELETE routes for audit rows. `restore_backup()` uses bulk
`session.execute(delete(EnvelopeAuditLog))`, which is a Core-level statement and
bypasses mapper events by design — so restore still works and this must be stated
in a comment next to both the listener and the restore call, or a future reader
will "fix" one of them into breaking the other.

Naming note: `event_type` is `String(24)` (not the prior attempt's `String(20)`)
so `template_applied` (16) and `closed_month_ledger_drift`-style future values
fit without a migration.

---

## 5. API contract

All routes behind `APIRouter(prefix="/envelopes", tags=["envelopes"])`, mounted
with `app.include_router(envelopes.router, prefix="/api")`.

**Route-ordering requirement**: declare every `/envelopes/templates...` route
**before** `/envelopes/{year}/{month}...`. `year`/`month` are typed `int` with
`ge`/`le` bounds so a non-integer segment fails with 422 rather than silently
matching a literal path. Add a test that asserts `GET /envelopes/templates`
still resolves to the template list (regression guard for this ordering).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/envelopes` | months that have envelope data: `[{year, month, is_closed, has_ledger_drift}]` |
| `GET` | `/envelopes/{year}/{month}` | full month status (§5.1) |
| `POST` | `/envelopes/{year}/{month}/open` | create the month row / set the tracking boundary (idempotent) |
| `PUT` | `/envelopes/{year}/{month}/allocations/{category_id}` | upsert one envelope: `planned_amount?`, `assigned_amount`, `rollover_positive?`, `rollover_negative?` |
| `DELETE` | `/envelopes/{year}/{month}/allocations/{category_id}` | remove the envelope row, releasing its assignment (audited) |
| `POST` | `/envelopes/{year}/{month}/moves` | `{from_category_id, to_category_id, amount, note?}` → 201 |
| `POST` | `/envelopes/{year}/{month}/apply-template/{template_id}` | plan only |
| `POST` | `/envelopes/{year}/{month}/fund` | `{template_id?, copy_plan_from?}` |
| `POST` | `/envelopes/{year}/{month}/fund-next-month` | alias for `fund(year, month+1)` |
| `POST` | `/envelopes/{year}/{month}/close` / `/reopen` | closure |
| `GET` | `/envelopes/{year}/{month}/audit` | ordered audit rows |
| `GET`/`POST` | `/envelopes/templates` | list / create |
| `PATCH`/`DELETE` | `/envelopes/templates/{template_id}` | replace items / delete |

Write endpoints return the **updated month status** (one round trip for the UI),
except `/moves` (201 + status) and the template CRUD (template representation).

### 5.1 Response schemas (`backend/app/schemas/envelope.py`)

```jsonc
// GET /envelopes/2026/8
{
  "year": 2026, "month": 8,
  "tracking_start": {"year": 2026, "month": 8},   // null when never opened
  "is_closed": false,
  "has_ledger_drift": false,
  "fx_incomplete": false,                          // §4.1
  "income": "100.00",                              // §4.3, this month only
  "assigned": "100.00",                            // this month only
  "available_to_assign": "0.00",                   // cumulative
  "items": [{
    "category_id": 4, "category_name": "Groceries", "category_color": "#22c55e",
    "category_icon": "shopping-cart", "is_unbudgeted": false,
    "planned_amount": "500.00", "assigned_amount": "100.00",
    "activity": "-50.00", "carried_in": "0.00", "available": "50.00",
    "is_overspent": false,
    "rollover_positive": true, "rollover_negative": true, "has_row": true
  }],
  "warnings": [{"code": "underfunded", "category_id": 4, "amount": "400.00"}]
}
```

`warnings` is a **computed** list (never persisted, except the drift comparison
which uses the stored snapshot). Codes, all with `code` / optional
`category_id` / optional `amount`:

| code | meaning | severity |
|---|---|---|
| `overspent` | `available < 0` | warning |
| `underfunded` | `assigned < planned` | info |
| `unbudgeted_spending` | activity on a category with no row | info |
| `refund_without_envelope` | §4.3 stray refund | info |
| `available_to_assign_negative` | cumulative available < 0 | warning |
| `fx_coverage_incomplete` | excluded non-KZT rows | warning |
| `income_before_tracking_start` | assignable income exists before `start` | info |
| `closed_month_ledger_drift` | §4.7, with both totals | warning |

`/audit` returns `[{id, event_type, category_id, from_category_id,
to_category_id, amount, note, created_at}]`.

### 5.2 Errors

| status | when |
|---|---|
| 400 | envelope on a non-expense / unknown category; move to the same category; move amount ≤ 0; template item on a non-expense category; allocation exceeding available to assign |
| 404 | unknown month for a write (PUT/DELETE allocation, moves, fund, close/reopen on a non-open month), unknown template |
| 409 | any envelope planning write while the month is closed (`detail` names the month) |
| 422 | schema validation (negative `assigned_amount`/`planned_amount`, `year`/`month` out of range) |

Error `detail` strings are plain English on the wire (existing convention, e.g.
`"Allocation exceeds money available to assign"`); the frontend maps them to
translated text via i18n keys, or falls back to the generic save-error string.

### 5.3 Write rules (normative)

- **Allocation PUT**: `delta = assigned_amount_new - assigned_amount_old`. Reject
  with 400 when `delta > available_to_assign(M)`; `delta <= 0` is always allowed.
  Upsert the row; create the month row if absent; emit one `allocation` audit row
  with `amount = delta`. Must be rejected with 409 when the month is closed.
- **Allocation DELETE**: allowed only for an existing row; audited with
  `amount = -assigned_amount`; the row is removed (a "released" envelope is
  simply absent).
- **Move**: `from != to`; both must have rows in `M`; `amount > 0`;
  `source.assigned_amount >= amount`. Apply `-amount` / `+amount`; one `move`
  audit row with the note. No income/expense row is touched (INV-3).
  Cross-month moves are out of scope: funding another month is `fund`/unassign,
  and the API rejects any attempt to express a move across months by construction
  (the month is in the path).
- **Close**: 409-free once; requires the month row to exist (404 otherwise).

---

## 6. Migration and backup/restore

### 6.1 Alembic migration

- New revision file
  `backend/alembic/versions/e1a4c7b9d302_add_envelope_budgeting.py`,
  `down_revision = "b7e2c4f19a35"` (verified head, §0). Use a **new** revision id;
  do not reuse the uncommitted `d9e4f6a7b821` from the reference worktree.
- `upgrade()`: create the five tables in dependency order
  (`envelope_months`, `envelope_templates`, `envelope_template_items`,
  `envelope_allocations`, `envelope_audit_logs`) with the unique constraints,
  indexes and CHECK constraints of §3. `server_default`s are required for the
  `Numeric`/`Boolean` columns so the migration is safe on a populated database.
- `downgrade()`: drop in exactly reverse order.
- The migration touches **no** existing table, so it is structurally reversible
  and **cannot move an account balance or a legacy budget** — that is the whole
  point of the separation in PLAN.md:306-307, and must be stated in the migration
  docstring. Downgrade does discard envelope data; the docstring must say so
  (the format is still version-2, so a downgrade + restore of a v2 backup
  containing envelope data is not meaningful — document the runbook: export →
  downgrade → upload/restore is expected to lose envelope rows).
- Verify with: `alembic upgrade head`, then `alembic downgrade -1`, then
  `alembic upgrade head` against the real Postgres, and rely on the existing
  `conftest` session fixture (which migrates a fresh `aurum_test` on every run)
  as the standing chain check.
- Register the models in `backend/app/models/__init__.py` **and** in the
  `from app.models import (...)` list in `backend/alembic/env.py`, or
  autogenerate/`Base.metadata` will be incomplete.

### 6.2 Backup payload

Add to `backend/app/schemas/backup.py`, keeping `aurum_backup_version = 2`:

- `EnvelopeMonthBackup(id, year, month, is_closed, closed_at,
  closed_activity_total)`
- `EnvelopeAllocationBackup(id, year, month, category_id, assigned_amount,
  planned_amount, rollover_positive, rollover_negative)`
- `EnvelopeAuditLogBackup(id, year, month, event_type, category_id,
  from_category_id, to_category_id, amount, note, created_at)`
- `EnvelopeTemplateBackup(id, name)`
- `EnvelopeTemplateItemBackup(id, template_id, category_id, planned_amount,
  rollover_positive, rollover_negative)`

and five `Field(default_factory=list)` lists on `BackupPayload`
(`envelope_months`, `envelope_allocations`, `envelope_audit_logs`,
`envelope_templates`, `envelope_template_items`) with the repository's standard
comment: *defaulted so a file exported before envelope budgeting existed still
imports cleanly under the same format version*. Do **not** bump the version — the
whole existing design is "add optional lists, keep version 2".

`envelope_months` **must** be included: without it, `is_closed` and the drift
snapshot are lost, the tracking boundary can move after a restore, and the same
database restored twice would compute different `available_to_assign`.

### 6.3 Restore

In `restore_backup()`:

- export: `select(...)` for all five tables, in the existing deterministic order;
- reference validation (`_validate_references`): allocation/template-item/audit
  category ids must exist in `payload.categories`; template item `template_id`
  must exist; enforce `(year, month, category_id)` uniqueness and
  `(template_id, category_id)` uniqueness explicitly, because the DB constraint
  will otherwise fail mid-restore with a raw IntegrityError;
- delete phase: `envelope_audit_logs`, `envelope_template_items`,
  `envelope_templates`, `envelope_allocations`, `envelope_months` **before**
  `categories` (FK order);
- insert phase: after `categories`, before nothing dependent;
- `_reset_sequence()` for all five tables (required — the backup carries explicit
  ids and the existing helper exists for exactly this);
- keep audit immutability intact: bulk `delete()` bypasses the ORM mapper events
  (§4.8) — comment it.

Privacy: the audit `note` is user-authored free text and `amount` is financial
data. They live only in the user's own database and in the user JSON backup, which
already contains every transaction, so this adds no new exposure class. Envelope
amounts, notes and category names must **never** reach container logs —
`app/core/audit.py:log_destructive()` stays limited to counts/ids, and no
envelope code calls it with money.

---

## 7. Frontend plan

New, additive; the legacy Budget page stays byte-identical.

| File | Change |
|---|---|
| `frontend/src/types/index.ts` | `EnvelopeMonth`, `EnvelopeItem`, `EnvelopeWarning`, `EnvelopeTemplate`, `EnvelopeAuditEvent` and input types |
| `frontend/src/api/envelopes.ts` | thin functions over `api.get/post/put/patch/delete`, mirroring `api/budgets.ts` |
| `frontend/src/hooks/useEnvelopes.ts` | `useEnvelopeMonth(y,m)`, `useEnvelopeMonths()`, `useSetAllocation`, `useDeleteAllocation`, `useMoveEnvelope`, `useCloseMonth`, `useReopenMonth`, `useTemplates`, `useApplyTemplate`, `useFund`, `useFundNextMonth`, `useEnvelopeAudit`; invalidations must include `["envelopes"]`, `["envelope-month"]` **and the previous month's** key (rollover edits change two months) and `["financial-alerts"]` |
| `frontend/src/components/envelopes/AvailableToAssignCard.tsx` | cumulative available, income/assigned breakdown, negative + pre-boundary warnings |
| `frontend/src/components/envelopes/EnvelopeTable.tsx` | `plan / funded / activity / available` columns; overspent and unbudgeted styling; progress = `available / planned` clamped |
| `frontend/src/components/envelopes/EnvelopeAssignModal.tsx` | assign + plan + two rollover switches; client-side clamp to available to assign with the server message as the source of truth |
| `frontend/src/components/envelopes/EnvelopeMoveModal.tsx` | from/to/amount/note, validates `amount <= source assigned` |
| `frontend/src/components/envelopes/EnvelopeTemplateModal.tsx` | create/apply/fund, showing unfunded shortfalls |
| `frontend/src/components/envelopes/EnvelopeAuditList.tsx` | event list, translated labels |
| `frontend/src/components/envelopes/EnvelopeWarnings.tsx` | warning codes → text; drift banner for closed months |
| `frontend/src/pages/EnvelopePage.tsx` | page shell: `MonthSelector` + `YearSelector` (reused), closed-month read-only state, close/reopen, fund-next-month |
| `frontend/src/App.tsx`, `frontend/src/lib/navigation.ts` | route `/envelopes` + `nav.envelopes` item |
| `frontend/src/lib/i18n.ts` | `envelope.*` keys in **both** `ru` and `en` (typed against `ru`, so a missing key breaks the build) |

Requirements:

- **mobile-first** (CLAUDE.md:4): card/list layout below `md`, table above; all
  actions reachable without horizontal scroll; numeric inputs use
  `inputMode="decimal"` and the existing `lib/decimal.ts` helpers for money maths
  — no raw float arithmetic (PLAN.md:331).
- **do not present envelope figures as account or budget balances**: no
  fetching/merging of `/budgets`, `/accounts`; the page must state in its empty
  state that an envelope balance is a plan, not money in an account.
- closed month: controls disabled with an explanatory note; `409` responses
  surface as a translated "month is closed" message, never a raw error.
- overspent and unfunded states must be distinguishable at a glance; both are
  already in `warnings`.
- RU and EN strings only; no hard-coded user-facing text.

---

## 8. Acceptance matrix

Test files: `backend/tests/test_envelopes.py` (new), `backend/tests/test_backup.py`
(extend), `backend/tests/test_insights.py` (extend), `backend/tests/test_budgets.py`
(unchanged, must stay green), frontend `*.test.ts(x)` under
`frontend/src/components/envelopes/` plus the existing i18n typecheck.

| # | Case | Level | Expected |
|---|---|---|---|
| A1 | allocation above available to assign | API | first `PUT` ok, second `PUT` 400 with "available to assign"; state unchanged |
| A2 | reducing / zeroing / deleting an allocation | API | always allowed; releases money; audited delta negative |
| A3 | cumulative available to assign across months | API | income in M+1 adds to M's carryover; `available_to_assign` matches the running sum |
| A4 | late income | API | income recorded after allocation raises `available_to_assign`; the allocation is not invalidated |
| A5 | next-month funding | API | `fund-next-month` assigns into M+1; `Σ assigned(M+1) ≤ available_to_assign(M+1)` |
| A6 | move neutrality | API | assigned shifts, `income`/`assigned` totals unchanged, no transaction row created, one `move` audit row |
| A7 | move guards | API | same category 400; amount > source assigned 400; missing envelope on either side 404/400 |
| A8 | rollover positive off / on | API | `carried_in` 0 vs. `available_prev` |
| A9 | rollover negative off / on | API | overspend carried as negative vs. dropped |
| A10 | rollover chain over ≥3 months + a gap month | API | values match the ascending fold; gap month rolls nothing out |
| A11 | refund on an expense category with an envelope | API | `activity` increases by the refund, `income` unchanged |
| A12 | refund on an expense category without an envelope | API | counted in `available_to_assign`, `refund_without_envelope` warning |
| A13 | split transaction | API | each line hits its own envelope; parent `category_id = NULL` contributes nothing; sums exact |
| A14 | parent/child, no child envelope | API | child activity rolls into the parent |
| A15 | parent/child, both have envelopes | API | child counted once, only in the child; no double funding |
| A16 | category move (edit a transaction's category) | API | activity moves between envelopes; totals conserved |
| A17 | closed month: allocation / move / fund | API | 409, nothing written, no audit row |
| A18 | closed month: reopen then edit | API | reopen 200 + `month_reopened` audit; edit then succeeds |
| A19 | closed month: ledger edit | API | transaction edit allowed; `has_ledger_drift` true and `closed_month_ledger_drift` warning carries both totals |
| A20 | template apply moves no money | API | `planned_amount` + flags set, `assigned_amount` unchanged, `template_applied` audit |
| A21 | fund respects the plan order and reports shortfall | API | assignments clamp to available; `unfunded` lists the shortfall; INV-1 holds |
| A22 | audit immutability | unit/API | ORM `update`/`delete` on an audit row raises; no route can mutate it |
| A23 | separation from accounts and legacy budgets | API | account balances and `/budgets/status` byte-identical before/after every envelope action; INV-2 |
| A24 | reporting-currency conversion | API | a non-KZT-account expense affects the envelope in KZT per the FX helper |
| A25 | FX coverage | API | a row with no resolvable KZT sets `fx_incomplete` + warning, and is not counted as 0 |
| A26 | tracking boundary | API | income before `start` is not assignable; `income_before_tracking_start` warning; `open` sets `start` |
| A27 | unbudgeted spending | API | category with activity and no row appears with `is_unbudgeted = true` and negative `available` |
| A28 | backup round trip | API | allocations, moves, templates, month closure + snapshot and audit survive export→import; figures identical |
| A29 | legacy backup import | API | a payload without any envelope keys imports, leaves envelope tables empty, and does not 500 |
| A30 | restore reference validation | API | allocation/audit/template item pointing at an unknown category is rejected with 400 before any write |
| A31 | migration reversibility | CLI | `alembic upgrade head` → `downgrade -1` → `upgrade head` on real Postgres, no error |
| A32 | no N+1 / cartesian product | test output | the envelope test run emits no `cartesian product` SQLAlchemy warning |
| A33 | insights alert | API | an overspent envelope in the current month yields the envelope alert |
| A34 | legacy budgets untouched | API | full `backend/tests/test_budgets.py` green, unchanged |
| F1 | assign modal clamps and shows the server rejection | vitest | clamp + translated error |
| F2 | available-to-assign card | vitest | cumulative value + negative/pre-boundary warning rendering |
| F3 | closed month read-only | vitest | controls disabled, translated closed note |
| F4 | move modal validation | vitest | rejects amount > source assigned |
| F5 | rollover switches round-trip | vitest | toggles send both flags and invalidate both months |
| F6 | i18n completeness | build | `npm run build` fails if any `envelope.*` key is missing |

Full-suite gates (Definition of Done, PLAN.md:383-387): `python -m pytest`
(backend, all green, ≥202 passed + new), `npm run test`, `npm run build`,
`alembic` up/down/up, and `graphify update .` after code changes (AGENTS.md).

---

## 9. Exact file list

Backend (new): `app/models/envelope.py`, `app/schemas/envelope.py`,
`app/services/envelope_service.py`, `app/api/routes/envelopes.py`,
`alembic/versions/e1a4c7b9d302_add_envelope_budgeting.py`,
`tests/test_envelopes.py`.

Backend (edit): `app/models/__init__.py` (export + `__all__`),
`alembic/env.py` (model import list), `app/main.py` (router),
`app/schemas/backup.py`, `app/services/backup_service.py`,
`app/services/insights_service.py` (one alert), `tests/test_backup.py`,
`tests/test_insights.py`.

Frontend (new): `src/api/envelopes.ts`, `src/hooks/useEnvelopes.ts`,
`src/pages/EnvelopePage.tsx`, `src/components/envelopes/*.tsx`,
`src/components/envelopes/*.test.tsx`.

Frontend (edit): `src/types/index.ts`, `src/lib/i18n.ts`,
`src/lib/navigation.ts`, `src/App.tsx`.

Docs (edit): `DOCS.md` (an `## Envelopes` section next to `## Budgets`, stating
that envelope balances are not account balances and that parent/child rollup
differs from `## Budgets`), `PLAN.md` (tick the milestone row only after merge).

---

## 10. Risks and trade-offs

1. **Cumulative available-to-assign can look "wrong" after a restore or a
   boundary mistake.** Mitigation: explicit `open`/tracking start, an out-of-window
   warning, and `envelope_months` in the backup.
2. **Subcategory envelopes change the parent's activity retroactively** when a
   child row is added. Deterministic and documented, but it is the one place where
   a write to one envelope changes another envelope's number; the UI must
   invalidate the whole month, not one row.
3. **Closed-month drift is detection, not prevention.** A closed month can show a
   different total than at close time. This is the deliberate, minimal coupling
   choice; the alternative (locking the ledger to envelopes) would break the
   ledger's independence and CLAUDE.md:2.
4. **Legacy `budgets` and envelopes will look like duplicates to a user.**
   Mitigated by copy in the UI and DOCS.md; a future opt-in "seed envelope plans
   from existing budgets" is deliberately NOT in this milestone (TODO.md).
5. **`Numeric(14,2)`** is the current convention but is on the
   `feature/financial-precision` radar; recorded, not pre-empted.

---

## 11. Deliberately open questions (for the design owner, not the workers)

1. Should a **gap month** (no row at all for a category) roll over the incoming
   carry and activity instead of hard-resetting? This design says "no row ⇒ no
   policy ⇒ hard reset", which is simple and predictable but can surprise a user
   who skips a month. Changing it later is a one-line change in `rollover_out`
   plus one test; the schema is unaffected either way.
2. Should `underfunded` be a warning or purely a UI highlight? This design keeps
   it in `warnings` as `info`.

Workers must implement §4 as written and raise these two only as comments on the
card, not as local re-decisions.
