import SwiftUI

/// Top-level routing: first the storage mode (chosen on first launch), then,
/// in server mode, the session phases. Each phase is a separate screen so the
/// app never shows finance UI without a confirmed session or an opened store.
struct RootView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        switch app.mode {
        case .none:
            ModeSelectionView(isOnboarding: true)
        case .server:
            ServerRootView()
        case .local:
            LocalRootView()
        }
    }
}

/// "My server": the original session flow (server setup → sign in →
/// workspace), unchanged.
private struct ServerRootView: View {
    @Environment(SessionStore.self) private var session

    var body: some View {
        content
            .task {
                // Runs on every switch into server mode, but only does work
                // while the session has not been established yet.
                guard session.phase == .launching else { return }
                await session.bootstrap()
            }
    }

    @ViewBuilder
    private var content: some View {
        switch session.phase {
        case .launching:
            LaunchView()
        case .launchFailed(let message):
            LaunchFailedView(message: message)
        case .serverSetup:
            ServerSetupView()
        case .login:
            LoginView()
        case .financeLocked:
            FinanceLockedView()
        case .ready:
            if let repository = session.repository, let workspace = session.activeWorkspace {
                MainTabView(repository: repository, canEdit: workspace.canEdit, local: nil)
                    // A workspace switch rebuilds every tab, so no screen can
                    // keep showing the previous workspace's numbers.
                    .id(workspace.id)
            } else {
                LaunchView()
            }
        }
    }
}

/// "Only on iPhone": the device store, no server involved.
private struct LocalRootView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        switch app.local {
        case .closed:
            LaunchView()
                .task { app.openLocalStore() }
        case .failed(let message):
            LocalStoreFailedView(message: message)
        case .ready(let repository):
            // A backup import replaces the whole ledger; every tab reloads
            // through the repository's ledger events, like after any write.
            MainTabView(repository: repository, canEdit: true, local: repository)
        }
    }
}

/// The device store could not be opened. Nothing is shown as if it were
/// empty; the user can retry or use the server instead.
private struct LocalStoreFailedView: View {
    @Environment(AppModel.self) private var app
    let message: String

    var body: some View {
        ContentUnavailableView {
            Label("local.failed.title", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button {
                app.openLocalStore()
            } label: {
                Text("action.retry").frame(minWidth: 160)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)

            Button {
                app.choose(.server)
            } label: {
                Text("mode.useServer")
            }
        }
    }
}

private struct LaunchView: View {
    var body: some View {
        VStack(spacing: Theme.Spacing.l) {
            Image(systemName: "a.circle.fill")
                .font(.system(size: 56))
                .foregroundStyle(.tint)
                .accessibilityHidden(true)
            ProgressView {
                Text("launch.connecting")
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// The saved server did not answer. Distinct from "signed out": the user
/// can retry or pick another server, and nothing pretends to be loaded.
private struct LaunchFailedView: View {
    @Environment(SessionStore.self) private var session
    let message: String

    var body: some View {
        ContentUnavailableView {
            Label("launch.failed.title", systemImage: "wifi.exclamationmark")
        } description: {
            VStack(spacing: Theme.Spacing.s) {
                Text(message)
                if let server = session.server {
                    Text(server.displayString)
                        .font(.footnote.monospaced())
                        .foregroundStyle(.secondary)
                }
            }
        } actions: {
            Button {
                Task { await session.bootstrap() }
            } label: {
                Text("action.retry").frame(minWidth: 160)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)

            Button {
                Task { await session.changeServer() }
            } label: {
                Text("server.change")
            }
        }
    }
}

/// The server reports finance_access_ready = false.
private struct FinanceLockedView: View {
    @Environment(SessionStore.self) private var session
    @State private var isChecking = false

    var body: some View {
        ContentUnavailableView {
            Label("locked.title", systemImage: "lock.shield")
        } description: {
            Text("locked.message")
        } actions: {
            Button {
                Task {
                    isChecking = true
                    await session.recheckFinanceAccess()
                    isChecking = false
                }
            } label: {
                if isChecking {
                    ProgressView()
                } else {
                    Text("locked.recheck").frame(minWidth: 160)
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(isChecking)

            Button {
                Task { await session.changeServer() }
            } label: {
                Text("server.change")
            }
        }
    }
}
