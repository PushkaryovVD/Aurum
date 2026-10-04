# Technical improvement backlog

## Restrict the shared backend database test harness to owned disposable databases

- **Problem:** `backend/tests/conftest.py` derives its server from application settings and uses a fixed `aurum_test` name with `DROP DATABASE ... WITH (FORCE)`, without verifying cluster ownership.
- **Why it matters:** an accidentally inherited remote/application configuration can destroy an unrelated test database or terminate another process's connections.
- **Suggested direction:** reuse the runtime/data-directory verification and create-only UUID/OID ownership checks from `unit_tests/test_core_workspace_migration.py`; cleanup without FORCE. The category-budget implementation was exercised through a scratch-only safe runner, not the unsafe default lifecycle.

## Complete privacy gates before enabling application authentication

- **Problem:** this slice scopes category-budget routes/status only. Other financial families and installation-wide callers of `get_budget_status` (for example insights/alerts) remain outside this bounded implementation.
- **Why it matters:** passing budget/core tests does not establish application-wide workspace isolation or approve auth activation.
- **Suggested direction:** deliver separate reviewed slices for remaining routes/aggregations and UI selection; keep broader Kanban/UI/auth-activation gates incomplete.

## Do not present unavailable dashboard data as a zero balance

- **Problem:** after a failed dashboard request, balance and statistic cards fall back to zero while category/transaction cards can show empty states.
- **Why it matters:** unavailable financial data must not be confused with a confirmed zero balance or a month without activity.
- **Suggested direction:** give dashboard cards explicit loading/error/empty states and preserve stale data only when its freshness is clearly indicated; add focused request-failure regression coverage.

## Split the frontend bundle by route

- **Problem:** the frontend production build warns that the main JavaScript chunk exceeds the recommended size.
- **Why it matters:** mobile users download code for unrelated financial screens before opening their chosen workflow.
- **Suggested direction:** review route-level lazy loading and loading/error boundaries, then measure the resulting initial bundle rather than suppressing the warning.

## Restore `@/` alias resolution in the Vite development server

- **Problem:** `npm run dev` currently fails during dependency scanning because Vite does not resolve the TypeScript `@/` path alias, even though the production build succeeds.
- **Why it matters:** local browser development and exploratory QA cannot reliably use the dev server and must fall back to a production preview.
- **Suggested direction:** configure an explicit Vite `resolve.alias` (or a maintained TypeScript-paths plugin), then verify both `npm run dev` and `npm run build` from a clean checkout.

## Refresh pinned Docker GitHub Actions for their Node.js runtime migration

- **Problem:** the successful GHCR image workflow emitted GitHub's October 3, 2026 warning that the pinned Docker login, metadata, and build-push actions still target deprecated Node.js 20 and are currently forced onto Node.js 24 runners.
- **Why it matters:** the workflow succeeds today, but an eventual removal of the compatibility shim could block image publishing and therefore CasaOS recovery/updates.
- **Suggested direction:** periodically review trusted immutable releases of the three Docker actions that natively support the current GitHub Actions runtime, update all pins together, and re-run the independent workflow review.
