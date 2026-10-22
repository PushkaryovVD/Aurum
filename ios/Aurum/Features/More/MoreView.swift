import SwiftUI

/// "More": the storage mode, then per mode — server: who is signed in,
/// workspace switch, server, sign out; device: reporting currency and
/// backup.
struct MoreView: View {
    @Environment(AppModel.self) private var app
    @Environment(SessionStore.self) private var session
    @State private var switchingTo: String?
    @State private var workspaceError: String?
    @State private var confirmSignOut = false
    @State private var confirmChangeServer = false
    @State private var isSigningOut = false
    @State private var isChoosingMode = false

    /// Set in "Only on iPhone" mode.
    let local: LocalRepository?

    init(local: LocalRepository?) {
        self.local = local
    }

    var body: some View {
        NavigationStack {
            List {
                storageSection

                if let local {
                    localSections(local)
                } else {
                    serverSections
                }

                Section {
                    LabeledContent {
                        Text(Self.appVersion)
                    } label: {
                        Text("more.version")
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle(Text("tab.more"))
            .sheet(isPresented: $isChoosingMode) {
                ModeSelectionView(isOnboarding: false)
            }
            .confirmationDialog(Text("more.signOut.confirm"), isPresented: $confirmSignOut, titleVisibility: .visible) {
                Button("more.signOut", role: .destructive) {
                    isSigningOut = true
                    Task {
                        await session.signOut()
                        isSigningOut = false
                    }
                }
                Button("action.cancel", role: .cancel) {}
            }
            .confirmationDialog(Text("server.change.confirm"), isPresented: $confirmChangeServer, titleVisibility: .visible) {
                Button("server.change", role: .destructive) {
                    Task { await session.changeServer() }
                }
                Button("action.cancel", role: .cancel) {}
            }
        }
    }

    // MARK: - Storage mode

    private var storageSection: some View {
        Section {
            LabeledContent {
                Text(app.mode == .local ? LocalizedStringKey("mode.local.title") : LocalizedStringKey("mode.server.title"))
                    .foregroundStyle(.secondary)
            } label: {
                Text("more.storage")
            }
            Button("more.storage.change") {
                isChoosingMode = true
            }
        } header: {
            Text("more.storage.header")
        } footer: {
            Text(app.mode == .local ? LocalizedStringKey("more.storage.localFooter") : LocalizedStringKey("more.storage.serverFooter"))
        }
    }

    // MARK: - Device mode

    @ViewBuilder
    private func localSections(_ local: LocalRepository) -> some View {
        Section {
            ReportingCurrencyRow(repository: local)
        } header: {
            Text("more.local.header")
        } footer: {
            Text("more.reportingCurrency.footer")
        }

        Section {
            NavigationLink {
                BackupView(repository: local)
            } label: {
                Label("backup.title", systemImage: "externaldrive")
            }
        } footer: {
            Text("more.backup.footer")
        }
    }

    // MARK: - Server mode

    @ViewBuilder
    private var serverSections: some View {
        if let identity = session.identity {
            Section {
                LabeledContent {
                    Text(identity.user.identifier)
                        .foregroundStyle(.secondary)
                } label: {
                    Text(identity.user.displayName)
                }
            } header: {
                Text("more.account")
            }

            if identity.workspaces.count > 1 {
                workspaceSection(identity)
            } else {
                Section {
                    LabeledContent {
                        Text(identity.activeWorkspace.displayName)
                    } label: {
                        Text("more.workspace")
                    }
                }
            }
        }

        Section {
            LabeledContent {
                Text(session.server?.displayString ?? "—")
                    .font(.footnote.monospaced())
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.trailing)
                    .textSelection(.enabled)
            } label: {
                Text("more.server")
            }
            Button("server.change") {
                confirmChangeServer = true
            }
        } header: {
            Text("more.connection")
        }

        Section {
            Button(role: .destructive) {
                confirmSignOut = true
            } label: {
                HStack {
                    Text("more.signOut")
                    if isSigningOut {
                        Spacer()
                        ProgressView()
                    }
                }
            }
            .disabled(isSigningOut)
        }
    }

    private func workspaceSection(_ identity: IdentitySession) -> some View {
        Section {
            ForEach(identity.workspaces) { workspace in
                Button {
                    select(workspace)
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(workspace.displayName)
                                .foregroundStyle(.primary)
                            Text(L10n.text("role.\(workspace.role)", fallback: workspace.role))
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        if switchingTo == workspace.id {
                            ProgressView()
                        } else if workspace.id == identity.activeWorkspace.id {
                            Image(systemName: "checkmark")
                                .foregroundStyle(.tint)
                                .accessibilityLabel(Text("more.workspace.active"))
                        }
                    }
                    .contentShape(Rectangle())
                }
                .disabled(switchingTo != nil)
            }
            if let workspaceError {
                Text(workspaceError)
                    .font(.footnote)
                    .foregroundStyle(Theme.negative)
            }
        } header: {
            Text("more.workspace")
        }
    }

    private func select(_ workspace: WorkspaceSummary) {
        workspaceError = nil
        switchingTo = workspace.id
        Task {
            do {
                try await session.selectWorkspace(workspace)
            } catch {
                if !error.isCancellation {
                    workspaceError = error.displayMessage
                }
            }
            switchingTo = nil
        }
    }

    private static var appVersion: String {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "?"
        let build = info?["CFBundleVersion"] as? String ?? "?"
        return "\(version) (\(build))"
    }
}
