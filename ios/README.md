# Aurum for iOS

A native SwiftUI client for a self-hosted Aurum server. It talks to the same
`/api` the web app uses — there is no separate mobile backend and no cloud
service in between. The server address is entered in the app; nothing about
your server, account or finances is baked into the build.

Status: MVP — overview, operations (list, search, month filter, details,
adding income/expense), accounts, workspace switching and sign-out.

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
    ├── App/                    AurumApp, RootView (phase routing), SessionStore
    ├── Networking/             APIClient, APIError, Endpoints, ServerAddress
    ├── Models/                 Codable DTOs mirroring frontend/src/types
    ├── Features/
    │   ├── ServerSetup/        server address entry + GET /api/auth/status probe
    │   ├── Login/              sign-in form
    │   ├── Main/               TabView shell
    │   ├── Dashboard/          "Overview" — monthly summary, balance, top categories
    │   ├── Transactions/       paged list, search, month filter, details
    │   ├── AddTransaction/     new income/expense sheet
    │   ├── Accounts/           balances grouped by currency
    │   └── More/               workspace, server, sign-out, version
    ├── Shared/                 money/date formatting, state views, theme, L10n
    └── Resources/              Assets.xcassets, en.lproj / ru.lproj strings
```

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
- **Nothing sensitive is persisted by the app**: only the server address
  (UserDefaults). The password exists in memory for the duration of the
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
| POST | `/api/transactions` | add operation |
| GET | `/api/accounts?include_archived=false` | accounts + balances |
| GET | `/api/categories` | categories for the add form |

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
6. Open Aurum, enter your server's `https://` address, sign in.

**Free Apple ID limits:** the signature is valid for **7 days**. After that
the app will not launch until it is re-signed — re-run step 4 with the same
(or a newer) `.ipa`; your server address is kept, and the session is restored
if it has not expired. A free Apple ID also allows only a few sideloaded apps
and app IDs at a time. A paid Apple Developer account extends signing to one
year.

## Not in the MVP

Editing/deleting operations, transfers, split transactions, tags, budgets,
goals, assets, crypto and reports — use the web app for those. Creating the
first owner account and accepting invitations also happen on the web.
