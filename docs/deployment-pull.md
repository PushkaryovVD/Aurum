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

The new workspace migrations support an empty financial installation and reject
unexpectedly populated legacy financial tables transactionally. They do not
assign an invented owner, backfill ownership, or delete existing records. If an
upgrade reports populated legacy tables, stop and retain the database rather
than clearing it or retrying with altered ownership constraints.

Before applying the first corrected Compose definition, confirm the project name, container names, database major version, and the actual PostgreSQL volume used by the current installation. Keeping the volume declaration text unchanged does not prove that a renamed Compose project will use the same physical volume. Do not delete/reinstall the CasaOS app as an automatic recovery step.

Never run `docker compose down -v` for an update. Do not switch an existing PostgreSQL data directory to another major version without a separate migration plan.

The default port bind is loopback. LAN/mobile exposure requires deliberate allowed-host and authentication configuration; do not silently broaden the bind address. Authentication is not enabled by this image-deployment procedure. Enabling application authentication is a separate rollout requiring a provisioned account, session secret, and usable login flow.

## CasaOS import

The canonical Compose includes `x-casaos` metadata and explicit service image/container names. A direct CasaOS API import may require resolved environment values and a concrete host port mapping; raw `${...}` expressions are not a portable CasaOS import artifact. Docker Compose deployment from a checkout and CasaOS registration are distinct operations. Do not claim that publishing this file repairs an already-installed CasaOS record.

At the end of the development stage, deliver the reviewed Compose definition and concise operator instructions. Do not include instance secrets in generated files or attachments.
