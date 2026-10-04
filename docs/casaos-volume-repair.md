# CasaOS exported PostgreSQL volume reference

The supplied Aurum export declares `aurum_pgdata` with physical name
`aurum_aurum_pgdata`, but the database mount refers to the literal source
`[object Object]`. Docker Compose rejects that export as an undefined-volume
project. This is a configuration-reference defect, not permission to delete a
volume, create an empty replacement, reinstall the app, or change PostgreSQL 16.

`deploy/casaos-volume-repair.yml` is a credential-free **overlay**, not a complete
Compose file and not a CasaOS import. It replaces the mount at the existing
PostgreSQL target and requires the export's declared physical volume to exist.
Docker Compose will not create a replacement volume when that external volume
is absent. The actual running container mount has **not** been verified: the
operator must confirm that its data is on `aurum_aurum_pgdata` before applying
this overlay. A matching declaration is not proof of the running mount.

From a checkout containing the reviewed release, with `Aurum.yaml` referring
to the existing export, validate the combination locally on the deployment host:

```sh
docker compose -f Aurum.yaml -f deploy/casaos-volume-repair.yml config --quiet
```

Do not share or commit the output of `config` without `--quiet`; resolved exports
can contain instance secrets. Validation alone neither starts services nor
repairs the saved CasaOS application record. If the operator subsequently applies
the combined files, use the same file pair for each Compose command and the
image-based `pull` / `up -d --no-build` procedure in `docs/deployment-pull.md`.
Do not use the export's local source `build` contexts for an image-based update.
A direct CasaOS editor/import repair is a distinct operator action; this overlay
does not prove CasaOS recognition or repair its serialized record automatically.

The overlay intentionally leaves ports, credentials, app-auth mode, PostgreSQL
major version, project identity and image references unchanged. In particular,
it does **not** make the supplied required-auth/production configuration ready
for multi-user use. The entry screen blocks financial UI in required-auth mode
while bootstrap and full financial isolation remain unfinished. Production
session entry requires HTTPS; plain HTTP to the LAN address is not sufficient.
Do not disable application authentication on a LAN-exposed instance with an
empty Basic Auth perimeter just to bypass this block.

The supplied export contains credentials. They are not reproduced in the
repository or this overlay. Treat shared credentials as exposed and plan a
controlled rotation. Changing only `POSTGRES_PASSWORD` in an existing volume's
Compose environment does not rotate the existing database-role password; never
attempt rotation by deleting the volume. HMAC rotation invalidates existing
sessions and invitations and should be coordinated with bootstrap/provisioning.
