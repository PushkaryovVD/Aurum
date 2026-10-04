# Aurum: deployment from published images

## Responsibility boundary

Development and verification happen in the repository and CI. Deployment is performed by the operator after the agreed development stage is complete. The coding agent must not connect to the deployment host, change CasaOS registration, inspect host credentials, or restart services without a new explicit request.

The canonical definition is `docker-compose.yml`. Backend and web have GHCR image references; their `build` contexts are retained for source-based development. Do not maintain a second hand-edited copy of the same service configuration.

## Image-based deployment

From the deployment checkout on the intended branch, retain the instance's existing environment configuration. Do not replace `.env` with `.env.example`: the latter contains placeholders, not instance credentials.

```sh
git pull --ff-only origin develop
docker compose config --quiet
docker compose pull
docker compose up -d --no-build
docker compose ps
```

These commands are an operator procedure, not evidence that deployment has occurred. `git pull` updates source/configuration; `docker compose pull` retrieves images; `up --no-build` applies the configuration without compiling source on the host.

For reproducible rollout, set `AURUM_BACKEND_IMAGE` and `AURUM_WEB_IMAGE` to the reviewed release's registry digests (or verified commit-specific tags). The default `develop` tags are mutable and intended for the test environment; they are not an immutable release identity. Verify both images belong to the same reviewed commit before deploying.

## Existing-installation safety

### Intermediate publication checkpoint — 2026-10-04

This checkpoint does not activate application authentication or provide complete
multi-user isolation. Keep `AURUM_APP_AUTH_REQUIRED` disabled: remaining financial
families and initial-account bootstrap/onboarding are not yet complete. Existing
outer-perimeter authentication is a separate configuration and is not changed.

### Login/access surface (bounded frontend slice)

The `/login` page is discoverable from the application. This is a new access
surface, not a redesign of every financial page and not an authentication
activation procedure. With application authentication disabled, the form is
disabled and never sends credentials; the existing single-installation finance
UI remains available after the explicit backend mode check. Basic Auth still
uses the browser's prompt and remains an independent outer perimeter.

The frontend first reads `GET /api/auth/status` (`Cache-Control: no-store`). A
missing, failed, or malformed response blocks the UI rather than assuming a
legacy permissive mode. Backend and frontend must therefore be upgraded as a
matched pair. The endpoint exposes only mode/transport metadata and always
returns `finance_access_ready: false`; it does not reveal account existence,
secrets, or database readiness.

For an already explicitly enabled backend with an already provisioned account,
the entry page can establish and revoke an identity session using the existing
`POST /api/auth/session`, `GET /api/auth/me`, and `DELETE /api/auth/session`
contract. There are no `/api/auth/login` or `/api/auth/logout` routes in this
version. The UI verifies session mutations by reading `/me` afterwards, retains
CSRF only in memory, and clears query cache on identity changes/logout. It does
not persist passwords, session capabilities, or CSRF in browser storage.

HTTPS is required for production session cookies. Non-production entry allows
plain HTTP only on exact loopback hosts (`localhost`, `127.0.0.1`, `[::1]`), not
on a LAN address. Configure TLS and the trusted reverse proxy separately; an
HTTPS frontend does not by itself prove the operator's proxy configuration is
correct. A missing/invalid cookie remains a failed session check, not success.

When `app_auth_required` is true, **all financial UI, settings queries, and
financial routes remain unmounted**, including after successful sign-in. The
screen explains that financial isolation and initial administrator account
bootstrap are incomplete. There is no public registration, reset, bootstrap,
or workspace picker in this slice. This frontend gate is not a substitute for
complete server-side authorization: do not enable application authentication
for normal financial use or claim complete multi-user security.

Before a future activation: finish and verify workspace isolation across every
financial family (including global insights), provide a reviewed administrator
bootstrap/onboarding procedure, verify production TLS/cookie/CSRF behavior,
and separately review finance-readiness activation in both backend and client.
No deployment defaults, Compose files, environment templates, or migrations
are changed by this login/access slice. An image-only Compose artifact may be
derived from the canonical definition for operator delivery; do not maintain
a second hand-edited canonical configuration.

### Migration and installation safeguards

The workspace migrations support both empty and populated pre-workspace
installations. Core financial rows and category budgets keep their original
values and relationships in the legacy `NULL` workspace namespace. They do not
assign an invented owner, create users, backfill ownership, or delete records.
Existing uniqueness constraints remain effective in that namespace. Repeating
`upgrade head` and the normal startup seeds does not replace existing rows.

Revisions `d2f6a8c1e940` and `e3b7c9d2a105` are corrected in place, with their
revision IDs and schema shape retained: a later revision cannot execute past
the old populated-table guards. Databases already at head need no new schema
revision for this compatibility correction. The category-budget migration
still locks both tables and rejects an existing legacy budget referencing an
already scoped category **before ALTER**, transactionally. On that error,
retain the database and investigate the relationship; do not clear tables,
invent an owner, disable guards, or transfer ownership to force an upgrade.

This is upgrade compatibility, not auth activation or application-wide
isolation. This repair does not change the installation's auth setting:
`finance_access_ready` remains false, and required-auth mode continues to block
financial access even after login. Do not disable required authentication on a
LAN-exposed instance without an appropriate perimeter just to bypass that block.

Before applying the first corrected Compose definition, confirm the project name, container names, database major version, and the actual PostgreSQL volume used by the current installation. Keeping the volume declaration text unchanged does not prove that a renamed Compose project will use the same physical volume. Do not delete/reinstall the CasaOS app as an automatic recovery step.

Never run `docker compose down -v` for an update. Do not switch an existing PostgreSQL data directory to another major version without a separate migration plan.

The default port bind is loopback. LAN/mobile exposure requires deliberate allowed-host and authentication configuration; do not silently broaden the bind address. Authentication is not enabled by this image-deployment procedure. Enabling application authentication is a separate rollout requiring a provisioned account, session secret, and usable login flow.

## CasaOS import

The canonical Compose includes `x-casaos` metadata and explicit service image/container names. A direct CasaOS API import may require resolved environment values and a concrete host port mapping; raw `${...}` expressions are not a portable CasaOS import artifact. Docker Compose deployment from a checkout and CasaOS registration are distinct operations. Do not claim that publishing this file repairs an already-installed CasaOS record.

At the end of the development stage, deliver the reviewed Compose definition and concise operator instructions. Do not include instance secrets in generated files or attachments.
