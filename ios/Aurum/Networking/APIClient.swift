import Foundation

enum HTTPMethod: String, Sendable {
    case get = "GET"
    case post = "POST"
    case patch = "PATCH"
    case put = "PUT"
    case delete = "DELETE"

    /// Methods the backend's CSRF guard lets through without a token.
    var isSafe: Bool { self == .get }
}

/// The one place that talks HTTP to an Aurum server.
///
/// It mirrors frontend/src/api/client.ts:
/// - the session is the backend's HttpOnly cookie, kept by the shared
///   HTTPCookieStorage (so it survives app restarts, like a browser's);
/// - every request carries `Origin` (the backend's same-origin check) and
///   `X-Aurum-Workspace` once a session is active;
/// - unsafe methods additionally carry `X-CSRF-Token`, held in memory only.
///
/// Main-actor isolated on purpose: requests are awaited off the main thread
/// by URLSession, and keeping the mutable session context (CSRF, workspace)
/// on one actor removes any chance of a data race in Swift 6 mode.
@MainActor
final class APIClient {
    let server: ServerAddress

    /// In-memory only; never written to disk.
    var csrfToken: String?
    var workspaceID: String?
    /// Called when a data request comes back 401 (session expired/revoked).
    var onUnauthorized: (@MainActor () -> Void)?

    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(server: ServerAddress) {
        self.server = server
        let configuration = URLSessionConfiguration.default
        configuration.httpCookieStorage = HTTPCookieStorage.shared
        // URLSession requests have no "main document", so the stricter
        // policy would silently drop the session cookie.
        configuration.httpCookieAcceptPolicy = .always
        configuration.httpShouldSetCookies = true
        // Financial data must never be served from a stale HTTP cache.
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.urlCache = nil
        configuration.timeoutIntervalForRequest = 30
        configuration.waitsForConnectivity = false
        self.session = URLSession(configuration: configuration)

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        self.decoder = decoder

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        self.encoder = encoder
    }

    // MARK: - Public request API

    /// Performs a request and decodes a JSON response.
    /// - Parameter isAuthRequest: true for the login call, whose 401 means
    ///   "wrong credentials" rather than "session expired".
    func send<Response: Decodable>(
        _ method: HTTPMethod,
        _ path: String,
        query: [URLQueryItem] = [],
        body: (any Encodable)? = nil,
        isAuthRequest: Bool = false,
        as type: Response.Type = Response.self
    ) async throws -> Response {
        let data = try await perform(method, path, query: query, body: body, isAuthRequest: isAuthRequest)
        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw APIError.decoding(String(describing: error))
        }
    }

    /// Performs a request whose response body is irrelevant (e.g. 204).
    func sendWithoutResponse(
        _ method: HTTPMethod,
        _ path: String,
        query: [URLQueryItem] = [],
        body: (any Encodable)? = nil
    ) async throws {
        _ = try await perform(method, path, query: query, body: body, isAuthRequest: false)
    }

    /// Forgets the session cookie(s) for this server on this device.
    func clearCookies() {
        let storage = HTTPCookieStorage.shared
        for cookie in storage.cookies(for: server.baseURL) ?? [] {
            storage.deleteCookie(cookie)
        }
    }

    // MARK: - Internals

    private func perform(
        _ method: HTTPMethod,
        _ path: String,
        query: [URLQueryItem],
        body: (any Encodable)?,
        isAuthRequest: Bool
    ) async throws -> Data {
        var request = URLRequest(url: try makeURL(path: path, query: query))
        request.httpMethod = method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(server.origin, forHTTPHeaderField: "Origin")
        if let workspaceID {
            request.setValue(workspaceID, forHTTPHeaderField: "X-Aurum-Workspace")
        }
        if !method.isSafe, let csrfToken {
            request.setValue(csrfToken, forHTTPHeaderField: "X-CSRF-Token")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            do {
                request.httpBody = try encoder.encode(body)
            } catch {
                throw APIError.decoding(String(describing: error))
            }
        }

        let result: (Data, URLResponse)
        do {
            result = try await session.data(for: request)
        } catch let urlError as URLError {
            throw Self.map(urlError)
        }
        let (data, response) = result

        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        if (200..<300).contains(http.statusCode) {
            return data
        }

        let detail = Self.detailMessage(from: data) ?? ""
        switch http.statusCode {
        case 401:
            if isAuthRequest {
                throw APIError.invalidCredentials(detail)
            }
            onUnauthorized?()
            throw APIError.unauthorized
        case 403:
            throw APIError.forbidden(detail)
        case 404:
            throw APIError.notFound(detail)
        case 422, 400:
            throw APIError.validation(detail)
        case 429:
            throw APIError.rateLimited
        case 503 where detail.localizedCaseInsensitiveContains("financial access"):
            throw APIError.financeLocked
        default:
            throw APIError.server(status: http.statusCode, message: detail)
        }
    }

    private func makeURL(path: String, query: [URLQueryItem]) throws -> URL {
        guard var components = URLComponents(url: server.baseURL, resolvingAgainstBaseURL: false) else {
            throw APIError.invalidResponse
        }
        components.path = components.path + "/api" + path
        if !query.isEmpty {
            components.queryItems = query
            // URLComponents leaves "+" alone, which servers decode as a space.
            components.percentEncodedQuery = components.percentEncodedQuery?
                .replacingOccurrences(of: "+", with: "%2B")
        }
        guard let url = components.url else {
            throw APIError.invalidResponse
        }
        return url
    }

    /// FastAPI errors are `{"detail": "text"}` or, for validation failures,
    /// `{"detail": [{"msg": "…", …}, …]}`.
    private static func detailMessage(from data: Data) -> String? {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        if let text = object["detail"] as? String {
            return text
        }
        if let list = object["detail"] as? [[String: Any]] {
            let messages = list.compactMap { $0["msg"] as? String }
            return messages.isEmpty ? nil : messages.joined(separator: "\n")
        }
        return nil
    }

    private static func map(_ error: URLError) -> Error {
        switch error.code {
        case .cancelled:
            return CancellationError()
        case .notConnectedToInternet, .networkConnectionLost, .dataNotAllowed, .internationalRoamingOff:
            return APIError.offline
        case .timedOut:
            return APIError.timedOut
        case .secureConnectionFailed, .serverCertificateHasBadDate, .serverCertificateUntrusted,
             .serverCertificateHasUnknownRoot, .serverCertificateNotYetValid, .clientCertificateRejected,
             .clientCertificateRequired, .appTransportSecurityRequiresSecureConnection:
            return APIError.insecureConnection
        default:
            return APIError.cannotReachServer
        }
    }
}
