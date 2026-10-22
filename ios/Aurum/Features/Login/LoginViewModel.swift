import Foundation
import Observation

@MainActor
@Observable
final class LoginViewModel {
    var identifier = ""
    /// Held only while the screen is up; cleared after every attempt and
    /// never written anywhere.
    var password = ""
    private(set) var isSigningIn = false
    private(set) var errorMessage: String?

    var canSubmit: Bool {
        !isSigningIn
            && !identifier.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !password.isEmpty
    }

    func signIn(using session: SessionStore) async {
        guard canSubmit else { return }
        errorMessage = nil
        isSigningIn = true
        let login = identifier.trimmingCharacters(in: .whitespacesAndNewlines)
        let secret = password
        password = ""
        defer { isSigningIn = false }
        do {
            try await session.signIn(identifier: login, password: secret)
        } catch {
            if error.isCancellation { return }
            errorMessage = Self.message(for: error)
        }
    }

    private static func message(for error: any Error) -> String {
        guard let apiError = error as? APIError else { return error.displayMessage }
        switch apiError {
        case .notFound:
            // The backend answers 404 when sign-in is not offered at all.
            return L10n.text("login.error.unavailable")
        case .forbidden:
            // 403 here is the same-origin/transport guard, not a wrong password.
            return L10n.text("login.error.origin")
        default:
            return apiError.userMessage
        }
    }
}
