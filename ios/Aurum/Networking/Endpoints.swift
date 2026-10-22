import Foundation

/// Typed wrappers for the backend routes this app uses. Paths are relative to
/// `/api` (APIClient adds the prefix). Keep one function per route so a
/// contract change touches exactly one place.
extension APIClient {
    // MARK: Auth

    func authStatus() async throws -> AuthStatus {
        try await send(.get, "/auth/status")
    }

    func login(identifier: String, password: String) async throws -> IdentitySession {
        try await send(
            .post,
            "/auth/session",
            body: LoginRequest(identifier: identifier, password: password),
            isAuthRequest: true
        )
    }

    /// Restores/validates the cookie session. Honors the X-Aurum-Workspace
    /// header, so it also confirms a workspace switch.
    func currentSession() async throws -> IdentitySession {
        try await send(.get, "/auth/me")
    }

    func logout() async throws {
        try await sendWithoutResponse(.delete, "/auth/session")
    }

    // MARK: Finance data

    func accounts(includeArchived: Bool = false) async throws -> [AccountWithBalance] {
        try await send(
            .get,
            "/accounts",
            query: [URLQueryItem(name: "include_archived", value: includeArchived ? "true" : "false")]
        )
    }

    func categories() async throws -> [LedgerCategory] {
        try await send(.get, "/categories")
    }

    func dashboardSummary(month: MonthRef) async throws -> DashboardSummary {
        try await send(
            .get,
            "/dashboard/summary",
            query: [
                URLQueryItem(name: "year", value: String(month.year)),
                URLQueryItem(name: "month", value: String(month.month)),
            ]
        )
    }

    func transactions(_ filter: TransactionFilter, page: Int, pageSize: Int) async throws -> TransactionPage {
        var query = [
            URLQueryItem(name: "page", value: String(page)),
            URLQueryItem(name: "page_size", value: String(pageSize)),
            URLQueryItem(name: "sort", value: "date_desc"),
        ]
        if let month = filter.month {
            query.append(URLQueryItem(name: "year", value: String(month.year)))
            query.append(URLQueryItem(name: "month", value: String(month.month)))
        }
        let search = filter.search.trimmingCharacters(in: .whitespacesAndNewlines)
        if !search.isEmpty {
            query.append(URLQueryItem(name: "search", value: String(search.prefix(255))))
        }
        return try await send(.get, "/transactions", query: query)
    }

    func createTransaction(_ input: TransactionInput) async throws -> LedgerTransaction {
        try await send(.post, "/transactions", body: input)
    }
}

/// What the Operations list is currently showing.
struct TransactionFilter: Hashable, Sendable {
    /// nil = all time.
    var month: MonthRef?
    var search: String
}
