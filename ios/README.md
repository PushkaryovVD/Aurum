# Aurum for iOS

A native SwiftUI client for Aurum with two independent storage modes, chosen
on first launch and switchable any time in *More*:

- **My server** — a client for your self-hosted Aurum server. It talks to the
  same `/api` the web app uses — there is no separate mobile backend and no
  cloud service in between. The server address is entered in the app; nothing
  about your server, account or finances is baked into the build.
- **Only on iPhone** — the whole ledger lives on the device (SwiftData). No
  server, no account, works offline.

The modes never sync and switching never deletes the other mode's data; data
moves between them through a backup file (see *Backup* below).

Status: overview, operations (list, search, month filter, details, adding,
editing and deleting income/expense/transfers), accounts (add, edit,
archive), workspace switching and sign-out (server mode), backup export and
import (device mode).

## Storage modes

| | My server | Only on iPhone |
| --- | --- | --- |
| Where the data is | your server's Postgres | `Application Support/LocalLedger/` on this iPhone |
| Network | HTTPS to your server | none |
| Overview computed by | the server (`dashboard_service.py`) | the app, same rules (`Domain/LedgerMath.swift`) |
| Exchange rates | official NBK rates on the server | none — see below |
| Opening balance of an account | not supported by the server | supported |
| Backup | web app → Settings → Backup & Restore | *More → Backup* (JSON, server-compatible) |

Both modes run the same screens and view models: every screen talks to the
`FinanceRepository` protocols (`Data/FinanceRepository.swift`), implemented by
`RemoteRepository` (over `APIClient`) and `LocalRepository` (over SwiftData).
The server-only flow (server address, `/api/auth/status`, sign-in,
workspaces) exists only in server mode. An install that already had a server
address from before modes existed starts in server mode without asking.

### What "Only on iPhone" means for your data

- The store is a SwiftData (SQLite) database in the app's Application Support
  directory. It is not in *Documents*, so it is not visible in the Files app,
  and CloudKit is explicitly off — nothing is uploaded anywhere.
- It **is** part of the iPhone's own backup: if iCloud Backup or a computer
  backup (Finder/iTunes) is enabled, the ledger is in it and comes back when
  that backup is restored.
- **Deleting the app deletes the data.** Export a backup regularly
  (*More → Backup*), and before anything that might reinstall the app.
- **File protection: `completeUntilFirstUserAuthentication`.** The store's
  directory is created with this class and every file in it is set to it
  after opening. The files are encrypted with a key that does not exist
  between a reboot and the first unlock. The stricter `complete` class was
  considered and rejected: it drops the key about 10 seconds after every
  lock, while SQLite keeps writing its WAL and checkpoints after the app
  moves to the background — those writes would then fail and could leave the
  store unusable or lose the last edit. This is also the class Apple uses by
  default for app data; here it is set explicitly. Use a device passcode:
  without one, no protection class encrypts anything.

### Same semantics as the server

The device ledger reproduces the server's rules (each function cites its
server counterpart):

- **Account balance** (`account_service.account_balances`): income adds,
  expense subtracts, a transfer subtracts `amount` from the source and adds
  `transfer_amount` (or `amount`) to the destination. Device-only: the
  account's opening balance is the starting point.
- **Overview** (`dashboard_service.get_dashboard_summary`): *real income* =
  the month's `income` operations, *spent* = `expense` operations; transfers
  are reported separately and are never income or spending; investment
  trades (`purpose = investment_trade`, only possible via an imported server
  backup) are left out; *net = real income − spent*; the balance is
  all-time across every account (archived included), per currency.
- **Top categories** (`category_rollup`): spending per top-level category, a
  subcategory rolls up into its parent, the breakdown lists children only
  when more than one fed the total, sorted by amount then sort order; the
  9th and later categories fold into "Other".
- **Write rules** (`schemas/transaction.py`, `routes/transactions.py`): a
  transfer needs a different destination and no category; a same-currency
  transfer credits exactly the debit, a cross-currency one needs the credited
  amount; expense needs an expense category, income an income one or an
  expense one (a refund); description required (≤ 255, first letter
  capitalized); a same-currency operation has one amount; an account's
  currency cannot change once it has operations.
- **Default categories** are exactly the server's seed
  (`backend/app/db/seed.py`): the same 8 expense + 9 income categories, names,
  colors and order, plus a starter checking account. Names are stored in
  English like on the server and translated for display (en/ru), as the web
  app does — in both modes.

**Not reproduced:** exchange rates. The server converts every operation to
KZT with official rates; the device has none. Instead the Overview reports
in the device's *reporting currency* (*More*, defaults to the region's
currency): operations on accounts in another currency are shown in the
account list and the balance breakdown but are not added to income/spending
or to the total, and the Overview names the currencies it left out — the
same way the server treats an operation without a rate. Split operations,
tags, budgets, goals, recurring payments, assets and crypto do not exist in
the device ledger yet.

## Backup (Only on iPhone)

*More → Backup* exports the device ledger to one JSON file (save it to Files,
iCloud Drive, AirDrop it to a computer) and imports one back. The format is
the server's backup format, version 2 (`backend/app/schemas/backup.py`).

- **Phone → server:** export here, then restore the file in the web app under
  *Settings → Backup & Restore*. Accounts, categories (with parents) and
  operations (types, amounts, currencies, transfers, dates, descriptions,
  notes) are restored; the reporting currency becomes the server's
  `app_settings.currency`. On the server side:
  - its restore **replaces the whole database**, and it is only available
    while the server runs without application sign-in
    (`app_auth_required = false`; with sign-in enabled the backup API answers
    503 by design);
  - operations on non-KZT accounts arrive without a KZT rate snapshot, so the
    server leaves them out of its reports until its exchange-rate sync (or a
    manual edit) fills it in — KZT accounts count immediately;
  - an account's **opening balance** has no server equivalent. It is exported
    as one operation per account (income for a positive balance, expense for
    a negative one), dated on the account's first operation, described
    "Opening balance" and marked with the note `[aurum-ios:opening-balance]`.
    On the server it therefore shows up as that month's income/spending;
    importing the file back into the app turns it into the opening balance
    again.
- **Server → phone:** export in the web app, import here. The app checks the
  file the way the server does before touching anything (format version 1
  or 2, unique ids, every account/category/parent reference resolves, valid
  types and dates, positive amounts), shows what the file contains and what
  will be lost, and replaces the device ledger **only after you confirm**, in
  a single save (on failure nothing changes). Carried over: accounts,
  categories, operations with `purpose`, merchant and notes, and the
  reporting currency. Not carried over: tags (the operations stay, the
  labels are dropped), split lines (a split operation is stored under its
  common parent category, so category totals stay exact; the sub-breakdown
  is lost), assets, budgets, goals, recurring payments, crypto, investments
  and cached exchange rates — the confirmation says how many records that is.
- **Phone → phone** (new device, reinstall): export, then import.

The backup file is plain, unencrypted JSON with all of your finances. Store it
somewhere you trust.

## Requirements

- iOS 17.0+ (iPhone).
- An Aurum server reachable over **HTTPS** with a certificate the iPhone
  trusts (a public CA such as Let's Encrypt, or a Cloudflare Tunnel). The app
  refuses `http://` addresses: the session cookie and your password travel
  over this connection, and iOS App Transport Security blocks plain HTTP
  anyway. A self-signed certificate will not work unless its CA is installed
  and trusted on the device.
- Use the same public address you open Aurum with in a browser: the backend
  checks the request `Origin` against its own public origin.

## Architecture

```
ios/
├── project.yml                 XcodeGen spec (the .xcodeproj is generated)
└── Aurum/
    ├── App/                    AurumApp, AppModel + StorageMode (mode routing),
    │                           RootView (mode + session phases), SessionStore
    ├── Data/
    │   ├── FinanceRepository   repository protocols, write models, ledger events
    │   ├── Remote/             RemoteRepository over APIClient, PATCH/POST bodies
    │   ├── Local/              SwiftData models, LocalStore (location, file
    │   │                       protection), LocalRepository, default categories
    │   └── Backup/             server-compatible backup format + codec
    ├── Domain/                 pure, storage-free rules: LedgerMath (balances,
    │                           overview, rollup, paging), LedgerRules (write
    │                           validation), LedgerSnapshot
    ├── Networking/             APIClient, APIError, Endpoints, ServerAddress
    ├── Models/                 Codable DTOs mirroring frontend/src/types (both modes)
    ├── Features/
    │   ├── Onboarding/         storage-mode choice (first launch, and from More)
    │   ├── ServerSetup/        server address entry + GET /api/auth/status probe
    │   ├── Login/              sign-in form
    │   ├── Main/               TabView shell (both modes)
    │   ├── Dashboard/          "Overview" — monthly summary, balance, top categories
    │   ├── Transactions/       paged list, search, month filter, details, edit/delete
    │   ├── AddTransaction/     new/edit income, expense or transfer sheet
    │   ├── Accounts/           balances grouped by currency, add/edit/archive
    │   ├── Backup/             export/import (device mode)
    │   └── More/               storage mode; server: workspace, server, sign-out;
    │                           device: reporting currency, backup; version
    ├── Shared/                 money/date formatting, category names, state views,
    │                           theme, L10n
    └── Resources/              Assets.xcassets, en.lproj / ru.lproj strings
```

### Adding the next areas (budgets, goals, recurring payments, assets, net worth)

Each area follows the same pattern without touching existing screens:

1. a `…Repository` protocol in `Data/FinanceRepository.swift`, added to the
   `FinanceRepository` composition;
2. `RemoteRepository`: typed `APIClient` endpoints for the server routes;
3. a SwiftData `@Model` in `Data/Local/LocalModels.swift` (listed in
   `LocalStore.schema`) and the `LocalRepository` methods;
4. any calculation as a pure function in `Domain/` over value structs,
   citing the server service it mirrors;
5. its array in `LedgerSnapshot` and its section in `Data/Backup/` (the
   server's backup already has `budgets`, `goals`, `recurring_transactions`,
   `assets`, …), so the backup stays a full round trip.

- **SwiftUI + Observation** (`@Observable`), no third-party dependencies.
- **Swift 6 language mode** with complete concurrency checking. View models
  and `APIClient` are `@MainActor`; DTOs are `Sendable` value types. URLSession
  does the network wait off the main thread.
- **Session** mirrors `frontend/src/api/client.ts`:
  - sign-in is `POST /api/auth/session`; the backend sets an HttpOnly session
    cookie kept by the system cookie store, so the session survives restarts
    until it expires or you sign out;
  - every request sends `Origin: <scheme://host[:port]>` and, once signed in,
    `X-Aurum-Workspace`; non-GET requests also send `X-CSRF-Token`;
  - at launch the app calls `GET /api/auth/status`, then `GET /api/auth/me`;
    a 401 shows the sign-in screen.
- **Nothing sensitive is persisted by the app in server mode**: only the
  server address and the chosen storage mode (UserDefaults). In device mode
  the ledger itself is, by design, stored on the device (see *Storage
  modes*). The password exists in memory for the duration of the
  sign-in request; the CSRF token lives in memory only. iOS password
  autofill works because the fields use the username/password content types.
- **Money** is decoded from the backend's decimal strings straight into
  `Decimal` (never `Double`) and formatted with `Decimal.FormatStyle.Currency`
  in the account's/report's own currency.
- **Honest states**: first load, error with *Retry*, genuinely empty, and
  "stale" (earlier data shown with a banner after a failed refresh) are all
  distinct — an error is never rendered as zero or as an empty list.
- **Localization**: English and Russian (`Resources/*.lproj/Localizable.strings`),
  chosen by the system language. Dynamic Type, Dark Mode and VoiceOver labels
  are supported.

### API endpoints used

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/auth/status` | server probe, finance readiness |
| POST | `/api/auth/session` | sign in |
| GET | `/api/auth/me` | restore/verify session, confirm workspace switch |
| DELETE | `/api/auth/session` | sign out |
| GET | `/api/dashboard/summary?year=&month=` | overview |
| GET | `/api/transactions?page=&page_size=&sort=&year=&month=&search=` | operations |
| POST | `/api/transactions` | add operation (income, expense, transfer) |
| PATCH | `/api/transactions/{id}` | edit operation (tags, splits, notes untouched) |
| DELETE | `/api/transactions/{id}` | delete operation |
| GET | `/api/accounts?include_archived=` | accounts + balances |
| POST | `/api/accounts` | add account |
| PATCH | `/api/accounts/{id}` | edit / archive account |
| GET | `/api/categories` | categories for the add form |

Device mode makes no network requests at all.

## Building

There is no committed `.xcodeproj`; it is generated from `project.yml` by
[XcodeGen](https://github.com/yonaskolb/XcodeGen).

### CI (no Mac needed)

`.github/workflows/ios-build.yml` runs on a GitHub-hosted macOS runner:

```sh
brew install xcodegen
cd ios
xcodegen generate
xcodebuild -project Aurum.xcodeproj -scheme Aurum -configuration Release \
  -sdk iphoneos -destination 'generic/platform=iOS' \
  CODE_SIGNING_ALLOWED=NO archive
```

The archive is built **unsigned** and packaged as `Aurum-unsigned.ipa`
(a `Payload/Aurum.app` zip), uploaded as a workflow artifact. No Apple
certificates, profiles or credentials are stored in the repository.

### Locally on a Mac

```sh
brew install xcodegen
cd ios && xcodegen generate && open Aurum.xcodeproj
```

Pick your own team under *Signing & Capabilities* to run on a device.

## Installing on an iPhone from Windows (Sideloadly, free Apple ID)

1. Download the `Aurum-unsigned-ipa` artifact from the latest successful
   *Build iOS app* workflow run and unzip it to get `Aurum-unsigned.ipa`.
2. Install **iTunes** (the version from apple.com, not the Microsoft Store
   one, if Sideloadly asks for it) and **Sideloadly** (sideloadly.io).
3. Connect the iPhone by USB, unlock it and tap *Trust this computer*.
4. In Sideloadly, drop in the `.ipa`, enter your Apple ID and press *Start*.
   Sideloadly signs the app with a free development certificate for your
   Apple ID. Use a secondary Apple ID if you prefer; the credentials go to
   Apple, not into this project.
5. On the iPhone: *Settings → General → VPN & Device Management* → trust your
   Apple ID's developer profile. On iOS 16+ also enable *Settings → Privacy &
   Security → Developer Mode* and restart when asked.
6. Open Aurum and choose a storage mode: for *My server* enter your server's
   `https://` address and sign in; *Only on iPhone* needs nothing else.

**Free Apple ID limits:** the signature is valid for **7 days**. After that
the app will not launch until it is re-signed — re-run step 4 with the same
(or a newer) `.ipa`; your server address and the device ledger are kept
(re-signing installs over the existing app), and the session is restored if
it has not expired. Deleting the app instead deletes the device ledger —
export a backup first. A free Apple ID also allows only a few sideloaded apps
and app IDs at a time. A paid Apple Developer account extends signing to one
year.

## Not in the app yet

Editing split operations (they can be viewed and deleted), tags, category
management, budgets, goals, recurring payments, assets, crypto and reports —
in server mode use the web app for those. Creating the first owner account
and accepting invitations also happen on the web. Planned: stage 2 —
budgets, goals and recurring payments; stage 3 — assets and net worth, in
both modes (see *Adding the next areas*).
