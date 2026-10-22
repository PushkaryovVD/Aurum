import Foundation

/// Every failure the networking layer can surface, already classified so the
/// UI can phrase it honestly ("server unreachable" is not "no data").
enum APIError: Error, Sendable, Equatable {
    /// No/invalid connection: offline, DNS, timeout, TLS.
    case offline
    case timedOut
    case cannotReachServer
    case insecureConnection
    /// 401 on a data request — the session cookie is gone or expired.
    case unauthorized
    /// 401 on the login request itself (wrong identifier or password).
    case invalidCredentials(String)
    case forbidden(String)
    case notFound(String)
    case rateLimited
    /// 503 "Financial access is not ready" — the server is up but finances
    /// are locked (e.g. encryption key not unlocked yet).
    case financeLocked
    case validation(String)
    case server(status: Int, message: String)
    case decoding(String)
    case invalidResponse
}

extension APIError: LocalizedError {
    var errorDescription: String? { userMessage }

    /// A sentence fit to show the user as-is.
    var userMessage: String {
        switch self {
        case .offline:
            return L10n.text("error.offline")
        case .timedOut:
            return L10n.text("error.timeout")
        case .cannotReachServer:
            return L10n.text("error.unreachable")
        case .insecureConnection:
            return L10n.text("error.tls")
        case .unauthorized:
            return L10n.text("error.unauthorized")
        case .invalidCredentials:
            return L10n.text("error.invalidCredentials")
        case .forbidden(let message):
            return Self.withDetail(L10n.text("error.forbidden"), message)
        case .notFound(let message):
            return Self.withDetail(L10n.text("error.notFound"), message)
        case .rateLimited:
            return L10n.text("error.rateLimited")
        case .financeLocked:
            return L10n.text("error.financeLocked")
        case .validation(let message):
            return Self.withDetail(L10n.text("error.validation"), message)
        case .server(let status, let message):
            return Self.withDetail(L10n.format("error.server", String(status)), message)
        case .decoding:
            return L10n.text("error.decoding")
        case .invalidResponse:
            return L10n.text("error.invalidResponse")
        }
    }

    private static func withDetail(_ headline: String, _ detail: String) -> String {
        let trimmed = detail.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.count < 300 else { return headline }
        return headline + "\n" + trimmed
    }
}

extension Error {
    /// The message to show for any error reaching the UI.
    var displayMessage: String {
        if let apiError = self as? APIError {
            return apiError.userMessage
        }
        return localizedDescription
    }

    /// Cancellation is not a failure: a view went away or a newer request
    /// replaced this one. Such errors must never be shown.
    var isCancellation: Bool {
        if self is CancellationError { return true }
        if let urlError = self as? URLError, urlError.code == .cancelled { return true }
        return false
    }
}
