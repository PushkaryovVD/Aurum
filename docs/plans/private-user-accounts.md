# Private user accounts and household workspaces

Status: implementation contract

Base: `develop` at `69a8114ac330703c764c02e202b3b6d19740f676`

## 1. Goal and non-goals

Aurum changes from one trusted installation-wide dataset to an invite-only,
multi-user application. Each authenticated person owns exactly one private
personal workspace and can belong to explicitly shared household workspaces.
The active workspace is a server-authorized context, never a client trust
boundary.

The first release supports three household roles:

| Role | Membership and workspace administration | Financial data |
|---|---|---|
| `owner` | create/revoke household invites; change non-owner roles; remove members; manage workspace | create/read/update/delete shared data |
| `editor` | none | create/read/update/delete shared data |
| `viewer` | none | read shared data only |

A personal workspace has exactly one member: its owner. It cannot receive
members, be converted into a household, or be selected by another user.
A household must retain at least one owner. Owner transfer is a separate,
explicit owner-only action and is not bundled with member removal.

This design deliberately does not implement any code, schema migration,
frontend, production configuration, backup/export/import/restore change, email
delivery, SSO, MFA, delegated access, granular permissions, or a way to move
personal records into a household. It defines bounded implementation work only.

## 2. Current-state inventory

The published base is a FastAPI application with SQLAlchemy 2 async sessions
and Alembic. `backend/app/main.py` directly mounts every router under `/api`.
Routers receive only `AsyncSession` through `app.api.deps.get_session`; there
is no authenticated principal, authorization dependency, or query scope. The
existing routes frequently load a row by integer primary key (`session.get`) or
select a whole table, so current IDs are installation-global and unauthenticated.

`backend/app/models` contains accounts, categories, tags and the
`transaction_tags` association; transactions and splits; assets and valuations;
budgets; goals and contributions; recurring transactions; categorization rules;
envelope months/allocations/audit/templates; crypto portfolios/holdings/
transactions/sync state; investment portfolios/securities/trades/dividends/
prices; application settings; and exchange-rate cache. `AppSettings(id=1)` and
`CryptoSyncState(id=1)` are explicit global singletons. `ExchangeRate` is an
installation-wide public-reference cache. Existing unique constraints (for
example tag name, category-independent envelope month, and transaction external
ID per account) assume one dataset and must be made workspace-aware where noted
below.

Startup currently calls three seed functions from the application lifespan.
They inspect the entire table and seed global categories, one account, and the
settings singleton. The replacement must seed a personal workspace during the
atomic account bootstrap/migration, never during arbitrary app startup.

The frontend is React 19/Vite/TypeScript with TanStack Query. `App.tsx` renders
the authenticated application shell unconditionally; `frontend/src/api/client.ts`
uses same-origin JSON fetches without credentials/CSRF handling; Topbar has only
the title. The existing RU/EN dictionary and mobile-first responsive shell are
the integration points for account and workspace UX.

nginx can generate HTTP Basic Auth from `AURUM_BASIC_AUTH_USER/PASSWORD` and
proxy the SPA/API. It protects an installation perimeter, not an application
identity. `/api/health` and `/auth-status.json` are intentionally public.
Basic Auth must remain optional after this feature; it is neither a user lookup
nor a source of roles or audit attribution.

Alembic imports models into metadata in `backend/alembic/env.py`; new models
must be registered there and in `app.models`. Existing migrations run on startup
through Compose. The current backup endpoint is global and must be disabled by a
fail-safe guard until a later, separately designed workspace-safe backup contract
exists.

## 3. Security and privacy threat model

Protected assets are credentials, sessions, invite capability tokens, personal
and household financial records, author/audit history, imports, exports and
configuration. An attacker may be unauthenticated, a member of a different
household, a viewer attempting a write, an editor attempting administration, a
member guessing numeric IDs/deep links, a browser affected by CSRF/XSS, or an
operator reading logs.

| Threat | Required control |
|---|---|
| Guessing a user, workspace, or record ID | Resolve membership server-side; scope every lookup/query before loading; return the same non-disclosing `404` for inaccessible scoped records; never accept `user_id`, `owner_id`, or arbitrary `workspace_id` to authorize data. |
| Cross-workspace foreign keys | Validate every referenced account/category/tag/asset/etc. in the active scope; use workspace columns, FKs, indexes, and composite constraints where relationships join scoped records. |
| Password theft/offline cracking | Use Argon2id with per-password salts and calibrated parameters; never retain plaintext, reversible encryption, passwords in exceptions, or password-derived audit fields. |
| Session theft/fixation | Generate opaque cryptographically random session secrets; store only a keyed hash; rotate session at login/password change; revoke on logout and membership removal; short idle and absolute expiry. Cookies are `HttpOnly`, `Secure` in HTTPS deployments, `SameSite=Lax`, `Path=/`; do not put bearer/session tokens in localStorage, URLs, or JSON logs. |
| CSRF | Cookie-authenticated unsafe methods require a synchronizer CSRF token in a custom request header. The server compares it in constant time to session state. Same-origin checks (`Origin`, then `Referer` fallback) complement but do not replace the token. Public invite acceptance uses its one-time token plus rate limiting and must not create an ambient authenticated action. |
| XSS | Keep tokens out of DOM/storage/URLs after invite acceptance; render user-entered names/descriptions as text, preserve React escaping, avoid `dangerouslySetInnerHTML`, and use a restrictive CSP at nginx in its own hardening slice. XSS remains able to issue same-origin requests, hence CSRF is necessary but insufficient. |
| Credential stuffing/brute force and token probing | Uniform login/recovery/invite errors; database-backed rate limit keyed by normalized identifier plus IP with bounded retention; limited, expiring invite use; audit security events without secrets. |
| Invite leakage/replay | Return plaintext invitation token only once to its creator. Persist a keyed HMAC/hash, expiry, use limit/count and revocation metadata, never the token. Consume atomically with a row lock/conditional update. Tokens in a link are cleared from browser history immediately after acceptance. |
| Logging/observability leakage | Redact `Authorization`, `Cookie`, `Set-Cookie`, CSRF headers, invitation/password fields and query values. Do not log balances, raw imported statements, records, session secrets, or invite tokens. Audit only IDs, event type, actor/workspace, outcome and timestamps. |
| Basic Auth confusion | Do not map its username to `User`; do not synthesize a session from it. It remains optional outer defence in depth and requires TLS when enabled. |

Use generic public messages such as “Unable to sign in” and “Invitation is not
available” for expired, revoked, exhausted, malformed and unknown tokens. The
member-management UI may show invited email only to an authorized owner; neither
login nor invitation acceptance may reveal whether an identifier exists.

## 4. Identity, sessions, invitations and dependencies

### 4.1 Recommended implementation

Use local email-as-login accounts (case-folded normalized identifier), an opaque
server-side session, and invitation links copied by a household owner. This
requires no external identity provider, mail service, JWT revocation list, or
browser token persistence, and suits the existing same-origin SPA/API deployment.
Email delivery/recovery is deliberately deferred: an invite is displayed once
for secure out-of-band delivery, while password reset remains disabled until a
verified delivery channel and its separate security design exist.

Add these dependencies after compatibility/security review:

| Dependency | Decision | Reason |
|---|---|---|
| `argon2-cffi` | Add | Mature Argon2id password hashing implementation; no home-grown KDF. Pin a tested compatible version. |
| `pwdlib[argon2]` | Do not add alongside `argon2-cffi` | It duplicates the password-hashing abstraction; choose one clear primitive. |
| JWT library | Do not add | Stateless browser JWTs complicate logout, session revocation and membership changes without benefit here. |
| Redis/rate-limit framework | Do not add in first slice | Postgres already exists. A small bounded `auth_rate_limits` table with atomic upsert/window logic is sufficient for one deployment; document replacement with shared rate limiting before horizontal scaling. |
| Email/SMS provider | Do not add | No verified recovery/invite-delivery channel has been selected. |

Configuration introduced in the authentication slice must include a deployment
secret used to HMAC sessions/invites, Argon2 tuning parameters, and session
idle/absolute lifetimes. Fail closed in non-development environments when the
secret is missing, default-like, or too short; never expose it from settings or
logs. Use `secrets.token_urlsafe(32)` or stronger entropy for raw capabilities.

### 4.2 Tables and invariants

| Table | Essential fields and invariants |
|---|---|
| `users` | UUID primary key; normalized login unique; display name; `password_hash`; `status` (`active`, `disabled`); timestamps. Never return `password_hash`. |
| `workspaces` | UUID primary key; `kind` (`personal`, `household`); display name; `created_by_user_id`; timestamps. A personal workspace has one immutable owner user. |
| `workspace_memberships` | UUID primary key; `workspace_id`, `user_id`, role, timestamps, `joined_at`, `revoked_at`; unique active membership per workspace/user. Check/trigger or service invariant: personal workspace has its owner as sole owner/member; a household has one or more active owners. |
| `workspace_invitations` | UUID primary key; `workspace_id`; intended normalized recipient identifier (not publicly queried); role limited to editor/viewer; token HMAC; `expires_at`; `max_uses` default 1; `uses`; `revoked_at`; creator and accepted-user references; timestamps. Owner-only creation/revocation. |
| `user_sessions` | UUID primary key; `user_id`; session-token HMAC; `csrf_secret`; created/last-seen/idle-expiry/absolute-expiry/revoked timestamps; optional privacy-minimized IP/user-agent hashes. Unique token HMAC. |
| `security_audit_events` | append-only event ID, actor user nullable, workspace nullable, event type/outcome, target IDs and timestamp; no secrets or financial payloads. |
| `auth_rate_limits` | keyed HMAC/bucket identity, window start, count, blocked-until; no plaintext login identifiers or raw IP retained. |

Use UUIDs for new identity/workspace/capability public identifiers. Existing
financial integer IDs may remain stable for migration compatibility; UUIDs do
not replace authorization. Add `workspace_id NOT NULL REFERENCES workspaces(id)
ON DELETE RESTRICT` to each scoped root and index `(workspace_id, id)` and common
list/filter orderings. Do not cascade-delete financial data when a membership or
workspace is revoked.

## 5. Scope, ownership, authorship and integrity rules

Every request gets a `RequestContext(user, membership, workspace, permission)`.
Only the server resolves this context. The client may provide an active workspace
identifier only through `X-Aurum-Workspace`; it is parsed as UUID and accepted
only if the current session has an active membership. A missing header selects
the user’s personal workspace for compatibility; an invalid/inaccessible header
returns the same `404` as any unavailable scoped resource. The chosen ID is a
selector, not authority.

| Family | Scope and relationship rule |
|---|---|
| Accounts, transactions, transaction splits, transaction tags | Account, transaction and tag are workspace-scoped. A transfer’s source and destination accounts must share the active workspace. Category/split/tag references must resolve in the same scope. Replace global transaction external-ID uniqueness with `(workspace_id, account_id, external_id)`. |
| Categories, tags, categorization rules | Workspace-scoped. Parent categories and a rule’s category must be in the same workspace. Replace global tag name and any category/rule uniqueness with workspace-scoped uniqueness. Seed defaults per newly created personal workspace; do not seed household workspaces automatically. |
| Budgets, envelopes, templates and envelope audit | Workspace-scoped. All category references share workspace. Make month/category and template/category constraints include workspace; make template names unique per workspace. Audit events add `actor_user_id` and immutable workspace ID. |
| Goals, contributions, recurring transactions | Root is workspace-scoped; child inherits through its root. Any referenced account/category must be active-workspace scoped. |
| Assets, valuations, investment portfolios, securities, trades, dividends, prices | Asset/portfolio roots are scoped. Every linked account, asset and cash transaction must be in the same workspace. Child rows inherit scope and are query-joined through the root. |
| Crypto portfolios, holdings, transactions, sync state | Portfolio/root is scoped; holdings/transactions inherit. Replace singleton sync state with one row per workspace, unique `workspace_id`. |
| App settings, insights, dashboard, net worth, cash flow, reports, advice | `AppSettings` becomes exactly one row per workspace (`workspace_id` unique), not `id=1`. All derived results query only active workspace roots. No cross-workspace rollups or search in v1. |
| Statement/CSV imports and imports’ temporary state | Every preview, idempotency check, file-processing job and commit is bound to workspace and actor. Account/category/tag mapping IDs are checked in scope at preview and commit. Uploaded source files remain ephemeral and never become cross-workspace artifacts. |
| Exchange rates | Installation-wide read-only cache, unscoped. It contains reference market data only; it must never join it to disclose financial data. Sync authorization can be owner-only initially or later moved to a background job. |
| Backup/export/import/restore | Disable endpoints with a deterministic `503 workspace backup unavailable` guard until a separate contract makes format, authorization, crypto and collision semantics workspace-safe. Do not silently export the old global dataset. |

All creation code sets `workspace_id` from `RequestContext`, not a JSON field.
All update/delete/detail queries begin with `WHERE Model.workspace_id ==
context.workspace.id AND Model.id == supplied_id`; never call `session.get(Model,
id)` for a scoped model. Use helpers such as `scoped_select(Model, context)` and
`require_scoped(Model, id, context)` to make omission reviewable. Services receive
`RequestContext`, not a bare database session. Eager relations remain scoped and
mutations validate foreign references through the same helper before flush.

Database relationships should add composite same-workspace foreign keys where
practical (for example transaction `(workspace_id, account_id)` to account’s
unique `(workspace_id, id)`). Where an inherited child does not carry
`workspace_id`, its parent must be locked/checked and all access joins through
that parent. The implementation must choose one convention consistently; adding
`workspace_id` to all roots plus all direct cross-root references is preferred
over relying only on ORM convention.

### Household transaction semantics

A household transaction’s `author_user_id` is assigned from the authenticated
request context on create, is immutable, and is visible to household members as
“created by”. It retains its author after that member leaves. A separate
append-only audit event records create/update/delete/import actions with actor,
workspace, target and timestamp; edits do not overwrite original authorship.
Editors may edit shared records in v1, including records authored by another
member; the audit trail makes that explicit. Viewers cannot write. Household
transaction totals, envelopes, budgets, reports and balances use only that
household’s records, so they affect household budgets normally.

Personal records are only in their private personal workspace. They are never
shown in a household, included in household balance/report/budget queries, copied
on workspace switching, or made visible by their author joining a household.

A future contribution feature is not a hidden scope exception. It needs a new
explicit `household_contributions` workflow: an author selects a household and
amount/category/date, sees a preview of exactly which limited fields become
shared and the household budget impact, then confirms an immutable allocation
record. The first implementation must not copy a personal transaction’s
merchant/notes/attachments by default, must not mutate the personal transaction,
and must create a distinct household financial record linked by opaque internal
provenance. It needs its own authorization, reversal/audit and privacy contract.

## 6. Authentication and authorization API contract

Keep `GET /api/health` public and add no financial/auth details to it. All
financial endpoints require an active application session irrespective of Basic
Auth. Exempt only the minimal public endpoints below.

| Endpoint | Contract |
|---|---|
| `POST /api/auth/session` | Login with identifier/password; generic failure; rate limited; sets rotated session cookie and returns current user/workspaces plus CSRF token. |
| `DELETE /api/auth/session` | CSRF-protected logout; revokes current session and clears cookie. |
| `GET /api/auth/me` | Current user and accessible workspace summaries, active workspace resolution and CSRF token. Never returns other users’ identifiers except authorized member display data. |
| `POST /api/auth/invitations/accept` | Public, rate-limited invitation acceptance. Valid token plus new account fields atomically creates user, personal workspace/default seed, household membership and session, then consumes invite. Generic unavailable failure otherwise. |
| `GET/POST/PATCH/DELETE /api/workspaces...` | Authenticated workspace metadata and household membership/invitation management. Personal workspace cannot be member-managed. Owner routes require `owner`; financial mutation routes require `editor` or `owner`; reads require membership. |
| Existing `/api/*` financial routes | Same route paths where possible. Add session/CSRF/context dependency globally or per router; remove client-supplied scope. Responses include only current workspace data. |

Do not add public “check email”, “list users”, “find workspace”, or invitation
lookup endpoints. Do not expose invitation status before acceptance. Return a
non-disclosing 404 for foreign scoped data and 403 only for a recognized member
whose role lacks an action, so ID probing cannot distinguish another workspace’s
record from an absent record.

The frontend API client must use `credentials: "same-origin"`, attach
`X-CSRF-Token` only to unsafe methods, refresh/clear session state on `401`, and
avoid retrying a failed unsafe request after session expiration. The workspace
header is added from in-memory authenticated state, never trusted by the server
and never persisted as authority in a URL.

## 7. Frontend and UX contract

Before session resolution, render only accessible RU/EN sign-in or invitation
acceptance screens; do not mount queries for financial pages. Invite acceptance
has no account-discovery step. On success it clears the raw invite fragment/query
from history using `history.replaceState`, then enters the authenticated shell.
Password fields use correct autocomplete attributes, permit password managers,
and show generic errors. No token/password reaches translation interpolation,
analytics, console logging, or localStorage.

After sign-in, add a workspace switcher in Topbar. It displays current workspace
name/kind and only memberships returned by `GET /api/auth/me`; personal spaces
are clearly marked private. Switching updates in-memory context, invalidates all
TanStack Query workspace-dependent keys, closes stale forms/modals, and returns
the user to a safe route. It must never optimistically display cached data from
the previous workspace. Household member/invite controls live in workspace
settings and render only for owners; viewers see a read-only badge and disabled
write entry points are supplemental UX, not authorization.

On 401/session expiry, clear cache and active context, preserve a safe
post-login destination only if it contains no record/workspace ID, and send the
user to sign-in. On 404/403, show generic localized unavailable/permission
messages without exposing another workspace name. Use keyboard-operable controls,
visible focus, semantic labels, no hover-only disclosure, 44px practical touch
targets, and layouts that work at 320/375/430px. Add every new string to RU and
EN dictionaries in the same slice.

## 8. Safe migration and rollback strategy

This is an upgrade of sensitive existing data and must be a rehearsed,
transactional migration, not a seed on application startup.

1. Add only additive auth/workspace tables, configuration validation and
   application feature flag `AURUM_APP_AUTH_REQUIRED=false`; do not route
   financial traffic through the new model yet.
2. Add nullable `workspace_id` and author fields to scoped tables, indexes and
   replacement workspace-aware unique constraints. Keep old constraints until
   backfill verification allows a controlled swap.
3. In one Alembic transaction, acquire an application migration lock, create a
   bootstrap owner from explicit deployment-only bootstrap configuration,
   create that user’s personal workspace/membership/settings/default categories
   only where absent, assign every existing scoped root to it, derive child
   scope through parent joins, set legacy transaction author to bootstrap owner
   only when author is unknowable, validate zero null/mismatched workspace IDs,
   then set `NOT NULL`, FKs and workspace-aware unique constraints. Never
   infer a household or use Basic Auth username as the owner.
4. If the bootstrap configuration is absent or any validation fails, abort the
   transaction and leave the pre-migration schema/data usable. Do not start an
   auth-required app against partially scoped data.
5. Deploy code that supports both flag states but enables required app sessions
   only after the migration marker and all scoped rows validate. Disable/global
   guard backup endpoints at the same release boundary.
6. Remove legacy global-seed behavior and the compatibility flag only after a
   successful upgrade window and recovery evidence. Retain a read-only
   migration-verification command/report containing counts, never records.

Alembic downgrade is not a data recovery plan: dropping workspace/auth columns
would erase identity/audit semantics. Before production rollout, take and test an
operator-controlled encrypted database backup under the existing operational
process. If post-enable defects appear, fail safe by disabling new logins and
household administration, preserving data, and restoring the tested database
snapshot or deploying a forward corrective migration. Do not “downgrade” by
silently collapsing multiple workspace records into one global dataset.

## 9. Test matrix and acceptance gates

| Area | Required tests |
|---|---|
| Password/session | Argon2 verify/rehash behavior; generic login failure; rate limits; login rotation; idle/absolute expiry; logout/revocation; disabled user; cookie flags; no token in response body/log capture. |
| CSRF | Unsafe request with no/wrong token fails; valid same-session token passes; safe GET does not require it; cross-origin origin check fails. |
| Invitations | Owner-only create/revoke; hash-only persistence; expired/revoked/exhausted/malformed token all generic; atomic one-use race permits exactly one acceptance; no user enumeration; accepted invite creates personal workspace plus household membership atomically. |
| Roles | Viewer cannot create/update/delete/import; editor cannot invite/manage members; owner can manage household; removing final owner/sole personal member fails; membership removal immediately removes access and sessions/context are revoked. |
| Isolation | For every resource family, two users/two workspaces prove list/detail/update/delete/child/nested/deep-link/guessed-ID paths return no foreign data; foreign account/category/tag/transfer/import IDs fail; reports/dashboard/net-worth/budgets/envelopes cannot aggregate across scopes. |
| Household behavior | Shared transaction is readable by household members, has immutable author and audit event, affects only household balance/budget; personal equivalent remains invisible and has no household budget effect; former member cannot read new/old records after removal. |
| Migration | Empty installation; populated legacy installation; rollback/fail-before-commit; zero null scope count; counts/sums preserved within bootstrap workspace; all existing FK relationships remain same-workspace; no accidental global seeds. |
| Frontend | Unauthenticated shell makes no finance queries; workspace change invalidates cache; session expiry clears it; CSRF header behavior; RU/EN strings; keyboard/mobile sign-in/invite/switcher at 320/375/430px. |
| Regression | Existing backend pytest and frontend Vitest/typecheck/build; migration upgrade test against a fixture at the published base; API contract tests for old routes under new auth/context dependency. |

Security acceptance is blocked by any query that loads a scoped row without a
context predicate, any client payload that creates scope, any logged
credential/capability, or any cross-workspace negative test failure.

## 10. Ordered implementation slices

1. **Foundation and migration rehearsal.** Add model/registering infrastructure,
   settings validation, migration lock/backfill fixture and verification command;
   leave application authentication disabled. Acceptance: legacy fixture upgrades
   atomically with counts/sums/relationships preserved and failure leaves no
   partial scope.
2. **Identity/session security.** Add user/session/rate-limit/audit primitives,
   Argon2id, secure cookie, CSRF dependency and public auth endpoints without
   open registration. Acceptance: session/CSRF/rate-limit/no-enumeration tests
   pass and Basic Auth remains an independent optional perimeter.
3. **Workspace/membership/invitation management.** Add personal bootstrap,
   household creation, roles and limited-use invitation acceptance. Acceptance:
   atomic account/personal/household invite flow, role/invite race tests and
   personal-workspace invariants pass.
4. **Core financial scope.** Scope accounts, categories, tags, transactions,
   imports, settings, dashboard/reports/cash flow/budgets/goals/recurring and
   all shared query helpers. Acceptance: exhaustive negative cross-workspace
   tests and household author/budget behavior pass.
5. **Advanced financial scope.** Scope assets, investment, crypto, envelopes,
   advice/insights and every remaining model/service; replace singleton
   assumptions. Acceptance: no global singleton remains except exchange rates;
   derived outputs are workspace-isolated.
6. **Frontend account/workspace UX.** Add sign-in, invitation, session-expiry,
   switcher and household settings flows with cache segregation and RU/EN/mobile
   acceptance. Acceptance: browser tests prove no unauthenticated query or stale
   workspace render.
7. **Rollout hardening.** Enable auth-required only after migration marker,
   guard legacy backup endpoints, add operational runbook/alerts and perform
   staged upgrade/recovery rehearsal. Acceptance: deployment fails closed on
   invalid config/scoping and recovery drill succeeds without data mixing.

No slice may begin before all acceptance criteria of its predecessor pass. A
future contribution/allocation workflow is a separately approved feature after
this sequence; it must not be smuggled into any workspace-isolation slice.

## 11. Decisions recorded

- Server-side opaque sessions, not JWTs or Basic Auth identities.
- Argon2id and a single password-hashing library; no bespoke crypto.
- Direct limited-use invitation links; no unselected email/reset provider.
- UUIDs for new identity/workspace/capability IDs; existing financial IDs can
  remain integers but become strictly workspace-scoped.
- Private personal workspace is the default and immutable privacy boundary.
- Household sharing is workspace-only; author attribution is immutable and
  audit records are append-only.
- Exchange-rate reference data remains global; all financial/application data is
  workspace scoped.
- Existing backup/export/import/restore is guarded unavailable rather than
  allowed to leak a global dataset until separately redesigned.
- `PLAN.md` already states this product contract precisely; no roadmap edit is
  required by this documentation slice.
