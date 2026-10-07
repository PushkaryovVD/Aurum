# Initial owner bootstrap

## Boundary

This is a single-use, operator-controlled setup ceremony for a new or legacy NULL-namespace Aurum installation with no users. It is not public registration, password reset, ownership migration, or finance-readiness activation. `finance_access_ready` remains false after completion.

## State machine

1. Compose creates a 48-byte installation HMAC key once in the private `aurum_auth_secrets` volume. It is mounted read-only for the unprivileged backend, never kept in PostgreSQL, Git, API responses, or logs.
2. When application authentication is required and no user exists, backend startup atomically creates one random capability with a short expiry. The backend log is the only raw-code delivery mechanism; neither `/api/auth/status`, the database, nor the UI reveals it.
3. A valid unexpired capability remains pending across backend restarts, but its raw value is never emitted again. Once it expires, the next backend start replaces it and emits a new value.
4. `GET /api/auth/status` reports only nonsecret setup state: whether setup is required and whether an unexpired code is currently available. It never discloses a code or secret.
5. A same-origin HTTPS request (or exact loopback HTTP outside production) to `POST /api/auth/bootstrap/initial-owner` can consume the capability once.
6. A successful transaction creates an active user, personal workspace, owner membership, default scoped records, a server-side opaque session/CSRF pair, and a success audit event, then removes the capability. Replays and competing submissions fail closed. `finance_access_ready` remains false.

## Threat controls

- The random code is bound to the installation HMAC key and compared with `hmac.compare_digest`.
- PostgreSQL transaction advisory locking serializes issuance and consumption before the singleton row exists; the row is also locked for update.
- Bootstrap failures are generic, recorded through a database-backed rate limiter, and audited without raw code or password values.
- Passwords use the existing Argon2id service. Browser credentials, code, session capability, and CSRF token are never persisted by the UI.
- **Narrow operational-log exception:** the raw capability is emitted only once through the backend container's standard startup log after its HMAC has committed. This log line is the deliberately approved operator-possession channel for this disposable capability; it is never stored, returned by an API, or logged elsewhere.
- The flow refuses production HTTP and cross-origin requests. It does not weaken the existing finance fail-closed gate.
- Legacy `NULL`-workspace financial data is deliberately untouched. Bootstrap creates only a new private workspace and its scoped defaults.

## Verification

Run backend unit checks and the disposable-PostgreSQL integration suite before release. The integration suite must use the approved create-only disposable runtime and must never target an application database. This bootstrap mechanism adds no operator-supplied bootstrap secret or database operation.
