# Aurum for iOS

A native iOS shell (Capacitor, WKWebView) around your self-hosted Aurum web
app. It loads your own instance, so sign-in cookies, CSRF and the same-origin
`/api` behave exactly as in Safari — no backend changes and no separate API
client. Your server address is never stored in the repository.

## Requirements

- A Mac with Xcode 26+ (Capacitor 8 uses Swift Package Manager; CocoaPods is not needed).
- Node.js 22+.
- Your Aurum instance reachable over **HTTPS** (for example through the
  Cloudflare Tunnel or Caddy setup in the main README). Plain `http://` works
  only with an explicit App Transport Security exception and is not recommended.

## Build

```bash
cd ios-app
npm install
AURUM_IOS_SERVER_URL=https://aurum.example.com npm run sync
npm run open          # opens ios/App/App.xcodeproj in Xcode
```

In Xcode: select the **App** target → *Signing & Capabilities* → choose your
Apple ID team (a free account is enough for your own device), pick your iPhone
or a simulator, then press Run.

Re-run `npm run sync` with the variable set whenever the server address
changes. The generated `ios/App/App/capacitor.config.json` is git-ignored.

## Notes

- The layout pads itself with `env(safe-area-inset-*)`, so the notch and home
  indicator are respected. These rules are no-ops in ordinary browsers.
- The Telegram Mini App script in `frontend/index.html` is harmless here.
- App icon and launch screen are Capacitor defaults. Replace the images in
  `ios/App/App/Assets.xcassets` to brand the app.
- Apps installed with a free Apple ID expire after 7 days and must be re-run
  from Xcode; a paid developer account removes that limit.
