// The iOS app is a native shell around the self-hosted Aurum web app. It
// loads the user's own instance (AURUM_IOS_SERVER_URL, an https origin) so
// cookies, CSRF and the same-origin /api all behave exactly as in Safari.
// The URL is deliberately NOT stored in the repo: each installation has its
// own address, and it is read from the environment when `cap sync` runs.
const serverUrl = process.env.AURUM_IOS_SERVER_URL;

/** @type {import("@capacitor/cli").CapacitorConfig} */
module.exports = {
  appId: "app.aurum.finance",
  appName: "Aurum",
  // Offline fallback shell; the live app comes from server.url below.
  webDir: "www",
  ios: {
    // Content runs edge to edge; frontend/index.html sets viewport-fit=cover
    // and the layout pads itself with env(safe-area-inset-*).
    contentInset: "never",
    backgroundColor: "#0b0b0b",
  },
  ...(serverUrl
    ? { server: { url: serverUrl, cleartext: serverUrl.startsWith("http://") } }
    : {}),
};
