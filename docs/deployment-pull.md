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

### Docker subnet collision

The default internal network is `172.31.254.0/29`. Some appliance-managed
hosts already reserve a broader overlapping range; Docker then rejects startup
with `invalid pool request: Pool overlaps with other one on this address space`.
Set the `AURUM_INTERNAL_*` values in the instance's existing `.env` to an unused
`/29`, with gateway `.1`, database `.2`, web `.3`, backend `.4`, and
auth-key-init `.6`; also update the trusted-proxy and loopback-client CIDRs to
that gateway/web address. The template contains a complete, internally
consistent example.

If Docker rejected startup before creating `aurum_internal`, apply the changed
environment with `docker compose up -d --no-build`. If the old internal network
already exists and services are attached to it, containers must be recreated on
the replacement network: run `docker compose down` (without `-v`), then
`docker compose up -d --no-build` and verify service health. Plain `down`
preserves named volumes, including the database and generated auth secrets;
`down -v` does not. Never resolve this error with `docker network prune` or
volume deletion.

### HTTPS before initial-owner setup

Initial owner setup and session creation reject HTTP from LAN or internet
clients. A generic `404` from an authentication endpoint on plain HTTP is an
intentional non-disclosing transport failure, not evidence that the route is
missing or the one-time code is wrong. For a public hostname, configure
`AURUM_DOMAIN` and use the TLS overlay:

```sh
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --no-build
```

The host's ports 80 and 443 must reach Caddy for certificate issuance. If the
internal Docker range was changed because of an overlap, configure the matching
`AURUM_TLS_*` values too; the TLS overlay has its own static network.

For reproducible rollout, set `AURUM_BACKEND_IMAGE` and `AURUM_WEB_IMAGE` to the reviewed release's registry digests (or verified commit-specific tags). The default `develop` tags are mutable and intended for the test environment; they are not an immutable release identity. Verify both images belong to the same reviewed commit before deploying.

## Existing-installation safety

### First-owner authentication checkpoint — 2026-10-06

Develop/test Compose activates application authentication and the first-owner
ceremony without an operator environment edit. This checkpoint still does not
activate financial access or claim complete multi-user isolation. Existing
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
matched pair. The endpoint reports finance ready only for legacy auth-disabled
mode; required-auth mode remains false. Its initial-owner flags intentionally
reveal whether the one-time setup ceremony is required/available, but never a
code, identifier, secret, or financial database state.

The develop/test Compose enables application authentication by default. On an
installation with no users, backend startup creates a single expiring setup
capability, persists only its HMAC, and emits the raw one-time code once in the
backend startup log after commit. The `/login` entry page consumes that code to
create the first owner, personal workspace, scoped defaults and opaque session.
No environment-supplied bootstrap secret is required.

After bootstrap, the entry page can establish and revoke an identity session
using the existing
`POST /api/auth/session`, `GET /api/auth/me`, and `DELETE /api/auth/session`
contract. There are no `/api/auth/login` or `/api/auth/logout` routes in this
version. The UI verifies session mutations by reading `/me` afterwards, retains
CSRF only in memory, and clears query cache on identity changes/logout. It does
not persist passwords, session capabilities, or CSRF in browser storage.

HTTPS is required for production session cookies. Non-production entry allows
plain HTTP only when the actual network peer is loopback, not merely when a
client-controlled `Host` header names localhost. The shipped TLS overlay sends
trusted transport metadata through nginx's un-published internal port; the
public HTTP port ignores browser-supplied forwarding headers. A missing/invalid
cookie remains a failed session check, not success.

When `app_auth_required` is true, **all financial UI and API routes remain
server-side unavailable**, including after successful sign-in. The routers stay
registered for stable URL contracts, but a global backend readiness dependency
returns `503 Financial access is not ready` before route logic or mutations run.
There is no public registration or password reset; first-owner bootstrap is a
one-time operator-controlled ceremony only. Do not claim complete multi-user
financial security until the separate finance-readiness review is complete.

Before a future finance activation: verify production TLS/cookie/CSRF behavior
and separately review finance-readiness activation in both backend and client.
The disposable PostgreSQL runtime used by integration tests is never a
deployment setting and is absent from Compose and `.env.example`. An image-only
Compose artifact may be derived from the canonical definition for operator
delivery; do not maintain a second hand-edited canonical configuration.

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
isolation. This repair does not change the installation's auth setting. In
required-auth mode, `finance_access_ready` remains false and financial access
stays blocked even after login; legacy auth-disabled mode reports readiness true.
Do not disable required authentication on a LAN-exposed instance without an
appropriate perimeter just to bypass that block.

Before applying the first corrected Compose definition, confirm the project name, container names, database major version, and the actual PostgreSQL volume used by the current installation. Keeping the volume declaration text unchanged does not prove that a renamed Compose project will use the same physical volume. Do not delete/reinstall the CasaOS app as an automatic recovery step.

Never run `docker compose down -v` for an update. Do not switch an existing PostgreSQL data directory to another major version without a separate migration plan.

The default port bind is loopback. LAN/mobile exposure requires deliberate
allowed-host, TLS and perimeter-authentication configuration; do not silently
broaden the bind address. Develop/test Compose enables application authentication,
provisions its HMAC material and presents the first-owner flow automatically.
Financial APIs remain backend-blocked in that required-auth mode.

## CasaOS import

The canonical Compose includes `x-casaos` metadata and explicit service image/container names. A direct CasaOS API import may require resolved environment values and a concrete host port mapping; raw `${...}` expressions are not a portable CasaOS import artifact. Docker Compose deployment from a checkout and CasaOS registration are distinct operations. Do not claim that publishing this file repairs an already-installed CasaOS record.

At the end of the development stage, deliver the reviewed Compose definition and concise operator instructions. Do not include instance secrets in generated files or attachments.
