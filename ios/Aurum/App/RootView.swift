import SwiftUI

/// Routes between the session phases. Each phase is a separate screen so the
/// app never shows finance UI without a confirmed session.
struct RootView: View {
    @Environment(SessionStore.self) private var session
    @State private var didBootstrap = false

    var body: some View {
        content
            .task {
                guard !didBootstrap else { return }
                didBootstrap = true
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
            if let client = session.client, let workspace = session.activeWorkspace {
                MainTabView(client: client, workspace: workspace)
                    // A workspace switch rebuilds every tab, so no screen can
                    // keep showing the previous workspace's numbers.
                    .id(workspace.id)
            } else {
                LaunchView()
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
