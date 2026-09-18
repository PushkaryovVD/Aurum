# Aurum development plan

This file is the source of truth for the fork's roadmap. Feature work starts
from `develop`; fixes use `fix/*` branches and product work uses `feature/*`
branches. A branch updates this checklist before it is merged.

## Delivery order

- [x] `fix/basic-auth` — native browser Basic Auth for the whole site
- [x] `feature/multicurrency` — KZT reporting currency and NBK/manual rates
- [x] `feature/bank-import` — currency-aware generic bank CSV import
- [x] `feature/investments` — manual securities, trades and dividends
- [ ] `feature/freedom-import` — previewed, idempotent Freedom Broker XLSX import

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

- Parse a redacted Tradernet global https://tradernet.global/ XLSX statement through upload, recognition,
  mapping, preview and atomic import stages.
- Report unknown sheet rows explicitly and make repeat imports idempotent.
- This milestone requires a representative redacted XLSX fixture.
- documentation about this https://tradernet.global/tradernet-api/auth-login

## Compatibility and quality gates

- Upgrade full JSON backup to v2 while retaining v1 import support.
- Every branch must pass backend tests, frontend tests/typecheck/build, Docker
  smoke checks and RU/EN mobile review before merge.
- Database changes use reviewed Alembic migrations. Imports are atomic and all
  user-facing text is translated in both languages.

## Backlog

- Statement closing-balance reconciliation and missing-operation detection.
- User-defined auto-categorization rules.
- Loans, mortgages and repayment schedules.
- Kazakhstan tax reporting after legal verification.
- Scheduled verified backups, financial calendar and privacy/audit tooling.
