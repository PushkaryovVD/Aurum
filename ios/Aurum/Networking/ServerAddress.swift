import Foundation

/// The user-entered Aurum server, validated and normalized.
///
/// Only HTTPS is accepted: the session cookie and the password travel over
/// this connection, and the backend itself refuses credentials over plain
/// HTTP outside a loopback dev setup. The address is stored in UserDefaults
/// (it is not a secret); nothing else about the session is persisted here.
struct ServerAddress: Hashable, Sendable {
    /// Scheme + host (+ port) + optional path prefix, no trailing slash.
    let baseURL: URL
    /// "https://host[:port]" — sent as the Origin header, which the backend's
    /// same-origin check compares against its own public origin.
    let origin: String

    private static let defaultsKey = "aurum.serverAddress"

    enum ValidationError: Error, Sendable {
        case empty
        case notHTTPS
        case invalid
    }

    /// Accepts "aurum.example.com", "https://aurum.example.com/",
    /// "https://host:8443/aurum". A missing scheme is taken as https.
    static func parse(_ input: String) -> Result<ServerAddress, ValidationError> {
        var text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return .failure(.empty) }
        if !text.contains("://") {
            text = "https://" + text
        }
        guard var components = URLComponents(string: text),
              let scheme = components.scheme?.lowercased(),
              let host = components.host, !host.isEmpty
        else { return .failure(.invalid) }
        guard scheme == "https" else { return .failure(.notHTTPS) }

        components.scheme = scheme
        components.host = host.lowercased()
        components.query = nil
        components.fragment = nil
        components.user = nil
        components.password = nil
        var path = components.path
        while path.hasSuffix("/") {
            path.removeLast()
        }
        // Someone pasting the API root itself ("…/api") means the same server.
        if path.lowercased().hasSuffix("/api") {
            path.removeLast(4)
        }
        components.path = path
        guard let url = components.url else { return .failure(.invalid) }

        var origin = "\(scheme)://\(host.lowercased())"
        if let port = components.port {
            origin += ":\(port)"
        }
        return .success(ServerAddress(baseURL: url, origin: origin))
    }

    /// What to show the user (and what is stored).
    var displayString: String { baseURL.absoluteString }

    // MARK: - Persistence

    static func loadSaved() -> ServerAddress? {
        guard let saved = UserDefaults.standard.string(forKey: defaultsKey) else { return nil }
        if case .success(let address) = parse(saved) {
            return address
        }
        return nil
    }

    func save() {
        UserDefaults.standard.set(displayString, forKey: Self.defaultsKey)
    }

    static func clearSaved() {
        UserDefaults.standard.removeObject(forKey: defaultsKey)
    }
}
