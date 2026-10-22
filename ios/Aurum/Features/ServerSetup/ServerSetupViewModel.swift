import Foundation
import Observation

@MainActor
@Observable
final class ServerSetupViewModel {
    var address: String
    private(set) var isChecking = false
    private(set) var errorMessage: String?

    init(initialAddress: String = "") {
        address = initialAddress
    }

    var canSubmit: Bool {
        !isChecking && !address.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    func submit(using session: SessionStore) async {
        errorMessage = nil
        let parsed = ServerAddress.parse(address)
        let server: ServerAddress
        switch parsed {
        case .success(let value):
            server = value
        case .failure(.empty):
            errorMessage = L10n.text("server.error.empty")
            return
        case .failure(.notHTTPS):
            errorMessage = L10n.text("server.error.https")
            return
        case .failure(.invalid):
            errorMessage = L10n.text("server.error.invalid")
            return
        }
        isChecking = true
        defer { isChecking = false }
        do {
            _ = try await session.connect(to: server)
        } catch {
            if error.isCancellation { return }
            errorMessage = Self.message(for: error)
        }
    }

    /// A 404 or an unparsable body means something answered, but it is not
    /// an Aurum API — say that instead of a generic HTTP error.
    private static func message(for error: any Error) -> String {
        guard let apiError = error as? APIError else { return error.displayMessage }
        switch apiError {
        case .notFound, .decoding:
            return L10n.text("server.error.notAurum")
        default:
            return apiError.userMessage
        }
    }
}
