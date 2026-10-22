import Foundation
import Observation

/// Owns the app-wide session lifecycle: which server, whether we are signed
/// in, and which workspace is active. Everything here is in memory except the
/// server address (UserDefaults) and the backend's HttpOnly cookie (system
/// cookie storage). The password and CSRF token are never persisted.
@MainActor
@Observable
final class SessionStore {
    enum Phase: Equatable {
        /// Checking the saved server and cookie session at launch.
        case launching
        /// The saved server could not be reached / answered unexpectedly.
        case launchFailed(String)
        case serverSetup
        case login
        /// The server is up, but it says finances are not accessible yet.
        case financeLocked
        case ready
    }

    private(set) var phase: Phase = .launching
    private(set) var server: ServerAddress?
    private(set) var client: APIClient?
    /// The finance data layer over `client`; recreated together with it.
    private(set) var repository: RemoteRepository?
    private(set) var identity: IdentitySession?
    /// Set when a data request reported an expired session, so the login
    /// screen can say why the user is there.
    private(set) var sessionExpired = false

    var activeWorkspace: WorkspaceSummary? { identity?.activeWorkspace }

    init() {
        server = ServerAddress.loadSaved()
    }

    // MARK: - Launch

    /// Restores the previous session if the cookie is still valid.
    func bootstrap() async {
        guard let server else {
            phase = .serverSetup
            return
        }
        phase = .launching
        let client = makeClient(for: server)
        do {
            let status = try await client.authStatus()
            guard status.financeAccessReady else {
                phase = .financeLocked
                return
            }
        } catch {
            if error.isCancellation { return }
            phase = .launchFailed(error.displayMessage)
            return
        }
        do {
            let session = try await client.currentSession()
            try apply(session, to: client)
            phase = .ready
        } catch APIError.unauthorized {
            phase = .login
        } catch APIError.financeLocked {
            phase = .financeLocked
        } catch {
            if error.isCancellation { return }
            phase = .launchFailed(error.displayMessage)
        }
    }

    // MARK: - Server

    /// Checks that `address` really is an Aurum server (GET /api/auth/status)
    /// before remembering it. Returns the status so the caller can explain a
    /// locked server.
    func connect(to address: ServerAddress) async throws -> AuthStatus {
        let probe = APIClient(server: address)
        let status = try await probe.authStatus()
        address.save()
        server = address
        _ = makeClient(for: address)
        sessionExpired = false
        phase = status.financeAccessReady ? .login : .financeLocked
        return status
    }

    /// Forgets the server (and any session with it) and returns to setup.
    func changeServer() async {
        await signOut()
        ServerAddress.clearSaved()
        server = nil
        client = nil
        repository = nil
        phase = .serverSetup
    }

    // MARK: - Sign in / out

    func signIn(identifier: String, password: String) async throws {
        guard let server else {
            phase = .serverSetup
            return
        }
        let client = makeClient(for: server)
        // A fresh login must not inherit a previous user's workspace header.
        client.workspaceID = nil
        client.csrfToken = nil
        let session = try await client.login(identifier: identifier, password: password)
        try apply(session, to: client)
        // Verify the cookie really round-trips before declaring success: a
        // proxy that strips Set-Cookie would otherwise fail on the first
        // data request instead of here.
        do {
            let confirmed = try await client.currentSession()
            try apply(confirmed, to: client)
        } catch {
            identity = nil
            client.csrfToken = nil
            client.workspaceID = nil
            throw error
        }
        sessionExpired = false
        phase = .ready
    }

    func signOut() async {
        if let client, identity != nil {
            // Best effort: the local session is dropped even if the server
            // cannot be told (offline); the cookie is cleared below anyway.
            try? await client.logout()
        }
        client?.clearCookies()
        client?.csrfToken = nil
        client?.workspaceID = nil
        identity = nil
        if server != nil {
            phase = .login
        }
    }

    /// Called by APIClient when any data request returns 401.
    func handleUnauthorized() {
        guard phase == .ready else { return }
        client?.csrfToken = nil
        client?.workspaceID = nil
        identity = nil
        sessionExpired = true
        phase = .login
    }

    // MARK: - Workspace

    /// Switches the active workspace and confirms it with the server.
    func selectWorkspace(_ workspace: WorkspaceSummary) async throws {
        guard let client, let identity, workspace.id != identity.activeWorkspace.id else { return }
        let previous = client.workspaceID
        client.workspaceID = workspace.id
        do {
            let session = try await client.currentSession()
            try apply(session, to: client)
        } catch {
            client.workspaceID = previous
            throw error
        }
    }

    // MARK: - Finance lock

    /// Re-checks whether a locked server has become ready.
    func recheckFinanceAccess() async {
        await bootstrap()
    }

    // MARK: - Helpers

    private func makeClient(for server: ServerAddress) -> APIClient {
        if let client, client.server == server {
            return client
        }
        let client = APIClient(server: server)
        client.onUnauthorized = { [weak self] in
            self?.handleUnauthorized()
        }
        self.client = client
        self.repository = RemoteRepository(client: client)
        return client
    }

    private func apply(_ session: IdentitySession, to client: APIClient) throws {
        guard session.isConsistent else {
            throw APIError.invalidResponse
        }
        client.csrfToken = session.csrfToken
        client.workspaceID = session.activeWorkspace.id
        identity = session
    }
}
