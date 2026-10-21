# Technical improvement backlog

## Avoid iOS focus zoom in authentication fields

- **Problem:** credential inputs inherit the labels' small text size, which may cause iOS Safari to zoom when a field receives focus.
- **Why it matters:** unexpected zoom can disrupt the mobile sign-in layout and make controls harder to reach.
- **Suggested direction:** apply explicit 16px-or-larger input text without conflicting shared utilities, and verify focus behavior on a real iOS browser.

## Exercise aborted and late authentication requests explicitly

- **Problem:** auth tests cover pending-request finance gating, but do not explicitly simulate unmount during status, session login/readback, and logout requests.
- **Why it matters:** a late response must not update an obsolete identity view or retain sensitive cached data.
- **Suggested direction:** add focused deferred-fetch tests asserting abort signals and suppression of late responses after unmount; keep network/session material memory-only.

## Explicit legacy ownership migration remains a separate deliverable

- **Current boundary:** populated legacy upgrades preserve financial rows in the `NULL` workspace namespace; they do not create an initial owner or transfer records. Compatibility tests cover repeated upgrades/startup seeds and transactional rejection of an already scoped budget category.
- **Remaining work:** design and independently review explicit administrator bootstrap and ownership backfill across every financial family, with invalid relationships failing closed. Do not infer ownership from existing categories or enable auth/readiness as part of this repair.

## Extend populated upgrade and downgrade regression coverage

- **Problem:** populated fixtures exercise core finances, budgets, settings, goals and assets, but recurring, crypto, investment, categorization-rule and envelope tables are empty. An installation already at head under the previous migration files is checked statically, and downgrade roundtrips use empty databases.
- **Why it matters:** broader linked fixtures will detect unintended changes in future migrations; scoped installations cannot treat downgrade as a general rollback because restoring global uniqueness may reject scoped duplicates.
- **Suggested direction:** add representative linked records for untouched families, an old-head no-op upgrade fixture, and populated NULL-only downgrade preservation tests. Keep these separate from auth activation and ownership backfill.

## Split the frontend bundle by route

- **Problem:** the frontend production build warns that the main JavaScript chunk exceeds the recommended size.
- **Why it matters:** mobile users download code for unrelated financial screens before opening their chosen workflow.
- **Suggested direction:** review route-level lazy loading and loading/error boundaries, then measure the resulting initial bundle rather than suppressing the warning.

## Refresh pinned Docker GitHub Actions for their Node.js runtime migration

- **Problem:** the successful GHCR image workflow emitted GitHub's October 3, 2026 warning that the pinned Docker login, metadata, and build-push actions still target deprecated Node.js 20 and are currently forced onto Node.js 24 runners.
- **Why it matters:** the workflow succeeds today, but an eventual removal of the compatibility shim could block image publishing and therefore CasaOS recovery/updates.
- **Suggested direction:** periodically review trusted immutable releases of the three Docker actions that natively support the current GitHub Actions runtime, update all pins together, and re-run the independent workflow review.

## Reconcile historical Alembic metadata drift

- **Problem:** `alembic check` reports pre-existing differences between ORM metadata and migrated PostgreSQL schemas for several historical indexes and the timezone metadata of workspace-membership timestamps. The same differences reproduce at published baseline `d0370c0`; the first-owner migration adds no new drift.
- **Why it matters:** persistent autogenerate noise can hide a future migration omission and prevents using `alembic check` as a clean release gate.
- **Suggested direction:** reconcile model indexes and timestamp types with the established schema in a dedicated migration-maintenance change, then verify populated upgrade compatibility and a clean autogenerate check without altering existing data.
