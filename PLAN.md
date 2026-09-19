# Aurum development plan

This file is the source of truth for the fork's roadmap. Feature work starts
from `develop`; fixes use `fix/*` branches and product work uses `feature/*`
branches. A branch updates this checklist before it is merged.

## Current state — resume here

_Last updated on `develop`._

### Where the work lives

`develop` is the working branch and now contains everything: `main` plus the
features below, merged in stack order. The feature branches are kept rather than
deleted, so each one is still reviewable on its own.

| Merged into `develop` | Contains |
|---|---|
| `feature/multi-currency-transactions` | Transaction-level currency, account currency, dashboard total balance |
| `feature/freedom-import` | Bank-statement import pipeline |
| `feature/auto-categorization` | Ordered categorization rules |

### Verified state

- `pytest`: **193 passed** (10 of them covering the rules, 8 the cross-rate endpoint).
- `vitest`: **58 passed**; `npm run build` clean.
- Both run against the merged `develop` tree.
- The Tradernet adapter was run against the real `bills/tradernet_table.xlsx`:
  155 rows, 104 importable, 0 warnings, dates 2021-03-24 … 2026-09-08.
- Migrations: head is `b7e2c4f19a35` (categorization rules). Every test run
  creates a fresh database and migrates it, so the chain is exercised on each
  run; the real database is migrated by the container entrypoint.

### Blocked, or waiting on a decision

1. **`develop` is ahead of `main` and has not been pushed**, so CI (GitHub
   Actions) has not run against any of this yet. Pushing is a deliberate step,
   not a side effect of merging.
2. **Tradernet trades/securities cannot be imported from the cash-movement
   export.** That file carries a commission row per trade (trade id, side,
   ticker) but no quantity and no price — those live in the broker's *trades*
   report, which is not in `bills/`. The Investments-side import needs that
   fixture before it can start.
3. **Kaspi/Halyk need OCR.** `bills/kaspi.pdf` is a scan with no text layer.
   `bills/freedom.pdf` has a text layer, but its table columns are reflowed and
   the layout is not reliable enough to parse.

### Next, in order

1. Run the rules while entering a transaction by hand. The backend already
   decides this on commit and on import preview; the manual form does not call
   it yet, so a typed-in transaction still starts with an empty category.
2. Investments import from the broker trades report — needs a fixture (see above).
3. `feature/kz-bank-statements` — Kaspi/Halyk, OCR phase.
4. The rest of the roadmap, in the order listed below.

## Delivery order

- [x] `fix/basic-auth` — native browser Basic Auth for the whole site
- [x] `feature/multicurrency` — KZT reporting currency and NBK/manual rates
- [x] `feature/bank-import` — currency-aware generic bank CSV import
- [x] `feature/investments` — manual securities, trades and dividends
- [x] `feature/transaction-currency-ux` — explicit currency context in the transaction form
- [x] `feature/multi-currency-transactions` — transaction-level currency with NBK cross rates
- [x] `feature/freedom-import` — previewed, idempotent Freedom Broker XLSX import
- [ ] `feature/kz-bank-statements` — Kaspi/Halyk PDF statement adapters
- [x] `feature/auto-categorization` — ordered rules applied to import preview and bulk apply
- [ ] `feature/envelope-budgeting` — monthly zero-based envelopes and rollover
- [ ] `feature/asset-depreciation` — depreciation and quarterly revaluation
- [ ] `feature/financial-precision` — end-to-end Decimal and rounding audit
- [ ] `feature/backup-automation` — scheduled encrypted PostgreSQL backups
- [ ] `feature/observability` — worker health, metrics and failure notifications
- [ ] `feature/arcane-deployment` — Arcane-ready Compose profiles and runbook

## Basic Auth

- Protect the SPA, static assets, API and backup endpoints at nginx level.
- Keep `/api/health` and `/auth-status.json` public.
- Use the browser's native `WWW-Authenticate` prompt; do not store or inject
  credentials in JavaScript and do not use a probe user.
- Preserve the explicit warning when authentication is disabled.
- Acceptance: unauthenticated UI/API return 401, valid credentials return 200,
  health remains public, and an unprotected instance shows the warning.

## Multicurrency

- KZT is the default reporting currency for new installations. Existing user
  settings are preserved.
- Transaction amounts remain in the account currency. Persist an immutable KZT
  conversion snapshot, optional original merchant currency details and a
  separate destination amount for cross-currency transfers.
- Load official historical rates from the National Bank of Kazakhstan over
  HTTPS, normalize quoted units, cache them, and allow manual/CSV rates to win.
- Never silently add unresolved currencies. Reports expose incomplete FX
  coverage until legacy non-KZT rows have been synchronized.
- Convert dashboard, cash flow, budgets, reports, alerts and net worth to KZT;
  account balances stay in their native currencies.

### Transaction currency UX (`feature/transaction-currency-ux`) — completed

The ledger currency of a transaction is the currency of its selected account.
It must not be an unrelated free-form currency, because that would make the
account balance ambiguous. The current form already follows this rule but does
not explain it, which makes the amount and rate fields look incomplete.

> Superseded by **Transaction-level currency** below — a transaction now carries
> its own currency, and the account-currency figure is the derived one. This
> checklist is kept as the record of what that milestone shipped.

- [x] Show the selected account currency directly beside `Amount` and in every
  account option (`Main Account · KZT`, `USD Card · USD`).
- [x] Rename the field to `Amount charged (KZT/USD/…)` after an account is selected;
  do not ask the user for a duplicate transaction-currency selector.
- [x] If the needed currency is unavailable, offer a shortcut to create another
  account instead of silently changing the currency of an existing account.
- [x] For a purchase priced in another currency, expose a clear `Purchase currency`
  block with original amount, original currency and merchant-to-account rate.
- [x] For a non-KZT account, load the historical NBK rate for the transaction date,
  show its effective date and a read-only `≈ … KZT` preview. A manual rate is an
  explicit override and its source remains visible when the transaction is read.
- [x] For cross-currency transfers, show two sides: `Sent` in the source account
  currency and `Received` in the destination account currency. Compute and show
  the effective source-to-destination rate before saving.
- [x] Keep the compact form for same-currency/KZT operations: advanced FX fields
  remain collapsed unless they are relevant.
- [x] Display account amount/currency, original amount/currency, KZT equivalent and
  rate source in transaction details and edit mode.
- [x] Acceptance: a KZT expense, USD-account expense, USD-priced purchase charged
  to a KZT card, and KZT→USD transfer can each be entered without guessing what
  any amount means; create/edit round trips preserve all currency fields.

### Transaction-level currency (`feature/multi-currency-transactions`)

A transaction is now denominated in its own currency rather than its account's,
superseding the rule above: paying 5 USD with a KZT card stores
`currency="USD"`, `transaction_amount=5` and `amount=2650` — what the account
was actually debited. `amount` therefore still drives every balance, report and
net-worth figure unchanged, and the two figures can only differ for a
foreign-currency operation.

- [x] Replace the `original_amount`/`original_currency`/`original_to_account_rate`
  triple with `currency` + `transaction_amount`, migrating existing rows: one
  that carried merchant-currency detail becomes denominated in that currency,
  every other row keeps the account's. `amount` is never rewritten, so no
  balance moves.
- [x] Resolve both fields server-side when a caller omits them (the account
  currency and `amount` respectively), and reject a same-currency row whose two
  figures disagree.
- [x] Expose the transaction currency and the account-side debit as separate
  fields in the form, with the NBK rate pre-filling the rate between them and
  the effective rate derived as `amount / transaction_amount`.
- [x] Keep reading the legacy `original_*` fields when importing a backup
  exported before this change, so such a file restores with its
  foreign-currency detail intact; never write them back out.
- [x] Carry the new fields through CSV import, the transactions list, the
  recurring "post now" action and the investment cash legs.
- Known limitation: the cross rate is resolved client-side from two NBK lookups
  divided through KZT. A server-side rate endpoint is out of scope here.

## Bank import

- Extend the existing generic CSV wizard with account amount/currency, original
  amount/currency, exchange rate and external transaction id.
- Prefer an external id for duplicate detection, falling back to the existing
  composite key. Direct bank credentials and scraping are out of scope.
- Add Kazakhstan bank presets only from real redacted exports.

## Investments

- [x] Add portfolios linked to investment cash accounts, securities, buy/sell
  trades, dividends and dated manual prices.
- [x] Use weighted-average cost. Buy fees enter cost basis; sell fees reduce
  proceeds. Show realized, unrealized and dividend returns separately and in
  total, with KZT snapshots for every event.
- [x] Generate linked cash transactions atomically. Trade principal changes cash
  but is excluded from ordinary income/expense reports; dividends, fees and tax
  remain visible cash flow.
- [x] Include investment entities and linked cash transactions in JSON backup v2.
- [x] Provide a responsive RU/EN UI for portfolios, positions, trades,
  dividends, manual prices and history deletion.
- [x] Online market prices are out of scope for v1.

## Tradernet Global import

- Parse a redacted Tradernet Global/Freedom Broker XLSX statement through
  upload, recognition, mapping, preview and atomic import stages.
- Report unknown sheet rows explicitly and make repeat imports idempotent.
- Import cash balances, securities, buy/sell trades, broker commissions,
  dividends, dividend withholding tax, bond coupons and supported corporate
  actions. Preserve the original statement row and external operation id for
  audit and duplicate detection.
- Treat coupons as investment income distinct from dividends and record their
  withholding tax separately. Unsupported corporate actions must remain in the
  preview as warnings, never disappear silently.
- Add a Kazakhstan tax-estimate report for realized securities results,
  dividends and coupons. The rate, residency, exchange/listing treatment,
  foreign-tax credit and calculation method are versioned settings, not a
  hard-coded universal rule. Label it an estimate, retain supporting source
  rows and require legal verification against the rules effective for the tax
  year before release.
- Keep management P&L (the existing weighted-average method) separate from tax
  P&L. Build a tax-lot ledger that can apply the legally required disposal
  order for the selected tax year, include eligible acquisition commissions
  in initial cost and reproduce every lot used by the estimate.
- Export a reconciliation report: opening cash + imported movements = closing
  cash, and opening position + trades/actions = closing position.
- This milestone requires a representative redacted XLSX fixture.
- API research starts from https://tradernet.global/tradernet-api/auth-login;
  credentials are never stored until an official, documented read-only flow is
  proven. XLSX remains the required v1 transport.

### Adapter architecture (`feature/freedom-import`)

Parsing is a registry of per-bank adapters (`app/importers`) rather than one
parser with a branch per bank: each format owns a module, and adding a bank
means adding a module and registering it. The pipeline is
parse → preview/edit → validate → commit, and the preview is editable — the
parser's reading is a proposal, and only what the user confirms is written.

- [x] Tradernet Global / Freedom Broker XLSX adapter, including the export's
  bare Excel serial dates and its "Reverted:" rows, whose direction comes from
  the amount's sign rather than the operation name.
- [x] Preview exposes every field the user may correct — date, description,
  amount, currency, direction, category — and writes nothing to the ledger.
- [x] Duplicate detection keyed on (destination account, bank operation id),
  matching the database's own uniqueness constraint; a row the export doesn't
  identify falls back to a content digest.
- [x] Rows that are not cash movements (reservations, trade settlements,
  internal transfers) stay visible in the preview with the reason, never
  silently dropped.
- [ ] Kaspi and Halyk statements are PDFs. Kaspi's is a scan with no text layer,
  so it needs OCR before an adapter is worth writing (see the
  kz-bank-statements milestone). The Freedom Bank card statement PDF does carry
  a text layer, but its table columns are reflowed and the layout is not
  reliable enough to parse without a visual model.

## Kazakhstan bank statement adapters (`feature/kz-bank-statements`)

- Build provider adapters on top of the existing universal import pipeline;
  normalized transactions must go through the same preview, mapping,
  validation, deduplication and atomic save stages as CSV.
- Add Kaspi and Halyk PDF presets only from redacted real statements covering
  both RU and KZ/EN variants. Detect statement version and fail explicitly when
  headers or totals no longer match the supported format.
- Phase 1 handles text PDFs. Phase 2 may add local OCR for scanned PDFs, with a
  confidence score and mandatory user confirmation for uncertain date/amount
  fields. Never send financial documents to a third-party OCR service by
  default.
- Validate opening balance + operations = closing balance and surface missing,
  duplicate or unparsed rows with PDF page/line references.
- Add a local paste/file parser for exported bank push-notification history.
  Direct mobile-notification access, scraping and storage of bank credentials
  remain out of scope.
- Provide a command-line converter from supported PDF to normalized Aurum CSV
  so parsing can be tested independently of the web UI.
- Acceptance fixtures are synthetic or irreversibly redacted and include
  refunds, transfers, fees, FX purchases and duplicate exports.

## Auto-categorization (`feature/auto-categorization`)

- Add ordered user rules over merchant, description, amount range, currency,
  account and transaction type. The first matching enabled rule wins.
- Support safe regular expressions with validation, execution limits and a
  plain `contains` mode for non-technical users; example: `Yandex Go` →
  `Transport / Taxi`.
- Run rules during import preview and manual transaction entry, show which rule
  matched, and allow one-click correction or creation of a more specific rule.
- Provide dry-run results before enabling or reordering rules. Never rewrite
  historical transactions without a separate previewed bulk action.
- Keep an optional classifier as a later local-only suggestion layer; it must
  expose confidence and never save categories without confirmation.

Delivered: the rule model and matcher, CRUD with explicit reordering, the
dry-run and the previewed bulk apply, and the rules page; the statement-import
preview fills in a category and shows which rule chose it, and the commit
re-runs the rules that need the destination account to decide. Not built yet:
running the rules as a transaction is typed by hand, the "make this rule more
specific" shortcut from a mismatch, and the optional local classifier.

## Envelope / zero-based budgeting (`feature/envelope-budgeting`)

- Add monthly income-to-envelope allocations, planned amount, activity,
  available balance and configurable positive/negative rollover.
- Enforce that allocations for a month cannot exceed money available to assign;
  transfers between envelopes do not create income or expense.
- Reuse the category hierarchy while keeping envelope balances separate from
  real account balances and from the existing spending-limit budget model.
- Support templates, next-month funding, overspending warnings and an audit log
  for every allocation/move.
- Acceptance covers late income, refunds, split transactions, category moves,
  rollover and editing an operation in a closed month.

## Property and vehicle valuation (`feature/asset-depreciation`)

- Extend assets with acquisition date/cost, optional residual value and one of:
  manual valuation only, straight-line depreciation or annual percentage.
- Generate projected values without overwriting recorded `AssetValuation`
  snapshots. A quarterly reminder asks the user to accept or replace the
  projection with a manual market revaluation.
- Show purchase cost, accumulated depreciation, latest market value and
  unrealized change separately. This is personal net-worth tracking, not
  accounting or a tax valuation.
- Online real-estate/vehicle price feeds are out of scope until a reliable,
  licensed Kazakhstan data source is selected.

## Financial precision and historical FX (`feature/financial-precision`)

- Audit every monetary, price, quantity and rate column plus all Python and
  TypeScript calculations. Database money/rates use explicit `NUMERIC` scales,
  Python uses `Decimal`, and the API transports decimals as strings. JavaScript
  `number` must not be used for financial arithmetic.
- Document rounding rules by value type: account money/cash postings, security
  quantities, instrument prices, FX rates and final KZT report values. Round at
  defined posting/report boundaries, never during intermediate calculations.
- Add migration guards for precision loss and property/boundary tests for tiny,
  very large and repeating-decimal values.
- Keep a dated KZT rate snapshot on every financial event and a historical
  cache keyed by requested date, effective official date and currency. Weekend
  fallback must retain both dates; manual/bank/imported rates retain provenance.
- Use KZT as the pivot for cross-currency reports. Missing historical coverage
  remains an explicit warning and is never substituted by today's rate.

## Self-hosting, backups and observability

### Arcane-ready Compose (`feature/arcane-deployment`)

- Publish a clean Compose configuration with named PostgreSQL and backup
  volumes, healthchecks, restart policies, resource guidance and separate
  `web`, `backend`, `db`, `worker` and optional `backup` services.
- Add an Arcane deployment example, `.env` validation, upgrade/rollback runbook
  and one-command migration check. Secrets stay in environment/secrets files,
  never in the image or repository.
- PostgreSQL remains the production database. SQLite compatibility is a
  separately evaluated lightweight profile only if migrations, concurrency,
  backup and all tests can provide equivalent guarantees.

### Backup strategy (`feature/backup-automation`)

- Schedule compressed PostgreSQL dumps plus Aurum JSON backup v2, with
  retention policies, checksums and optional client-side encryption.
- Support local volume first, then S3-compatible targets such as Backblaze B2
  or MinIO using least-privilege credentials. Uploads are retried and failures
  are visible; a failed remote upload must not delete the newest local backup.
- Add a restore command, version compatibility checks and an automated periodic
  restore drill into an isolated database. A backup is not marked verified
  until restore and integrity checks pass.

### Metrics and health (`feature/observability`)

- Keep the public liveness endpoint minimal and add an authenticated readiness
  endpoint covering database connectivity, migrations and worker heartbeat.
- Record last success, duration and error for NBK sync, imports, backups and
  future Tradernet jobs. Expose privacy-safe Prometheus metrics without account
  names, balances, merchants or holdings.
- Add optional webhook/Telegram notifications for actionable failures with
  cooldown and recovery messages. Document Uptime Kuma checks for web liveness
  and authenticated readiness.
- Health status must never leak credentials, portfolio values or raw exception
  traces.

## Compatibility and quality gates

- Upgrade full JSON backup to v2 while retaining v1 import support.
- Every branch must pass backend tests, frontend tests/typecheck/build, Docker
  smoke checks and RU/EN mobile review before merge.
- Database changes use reviewed Alembic migrations. Imports are atomic and all
  user-facing text is translated in both languages.

## Backlog

- Statement closing-balance reconciliation and missing-operation detection.
- Loans, mortgages and repayment schedules.
- Financial calendar and privacy/audit tooling.
