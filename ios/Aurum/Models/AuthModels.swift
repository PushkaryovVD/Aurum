import Foundation

// Mirrors backend/app/schemas/auth.py and frontend/src/lib/authSession.ts.
// Keys arrive in snake_case and are converted by APIClient's decoder
// (.convertFromSnakeCase), so property names are their camelCase forms.

/// GET /api/auth/status — public, unauthenticated readiness contract.
struct AuthStatus: Decodable, Sendable {
    let appAuthRequired: Bool
    let financeAccessReady: Bool
    let sessionTransport: String?
    let initialOwnerBootstrapRequired: Bool?
    let initialOwnerBootstrapAvailable: Bool?
}

struct SessionUser: Decodable, Sendable, Hashable {
    let id: String
    let identifier: String
    let displayName: String
}

struct WorkspaceSummary: Decodable, Sendable, Hashable, Identifiable {
    let id: String
    let displayName: String
    /// "personal" | "household"
    let kind: String
    /// "owner" | "editor" | "viewer"
    let role: String

    /// Viewers can read but every mutation is refused with 403 server-side,
    /// so the UI hides write actions up front instead of failing later.
    var canEdit: Bool { role == "owner" || role == "editor" }
}

/// Response of POST /api/auth/session and GET /api/auth/me.
struct IdentitySession: Decodable, Sendable {
    let user: SessionUser
    let csrfToken: String
    let workspaces: [WorkspaceSummary]
    let activeWorkspace: WorkspaceSummary

    /// Same invariant the web client enforces in parseSession: the active
    /// workspace must be one this session can actually reach.
    var isConsistent: Bool {
        !csrfToken.isEmpty && workspaces.contains { $0.id == activeWorkspace.id }
    }
}

/// Body of POST /api/auth/session. The password lives only in this value for
/// the duration of the request and is never persisted.
struct LoginRequest: Encodable, Sendable {
    let identifier: String
    let password: String
}
