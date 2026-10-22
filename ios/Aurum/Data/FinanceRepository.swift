import Foundation
import Observation

// The data layer every finance screen talks to. Two implementations exist:
// RemoteRepository (the user's own server over APIClient) and
// LocalRepository (SwiftData on this iPhone). Screens and view models only
// ever see these protocols, so both storage modes share the same UI.
//
// Each area of the ledger is its own small protocol. Later areas (budgets,
// goals, recurring payments, assets, net worth) are added the same way: a new
// `…Repository` protocol, one conformance per implementation, and an entry in
// the `FinanceRepository` composition below — existing screens are untouched.
//
// Everything is main-actor isolated: APIClient already is, and SwiftData's
// ModelContext is used from the main actor only. Values crossing the
// protocol are the Sendable DTOs from Models/.

@MainActor
protocol AccountRepository: AnyObject {
    /// Live balances in each account's own currency.
    func accounts(includeArchived: Bool) async throws -> [AccountWithBalance]
    func createAccount(_ input: AccountInput) async throws -> AccountWithBalance
    func updateAccount(id: Int, _ input: AccountInput) async throws -> AccountWithBalance
    /// The server has no opening balance; only the on-device store does.
    var supportsInitialBalance: Bool { get }
}

@MainActor
protocol CategoryRepository: AnyObject {
    func categories() async throws -> [LedgerCategory]
}

@MainActor
protocol TransactionRepository: AnyObject {
    func transactions(_ filter: TransactionFilter, page: Int, pageSize: Int) async throws -> TransactionPage
    func createTransaction(_ draft: TransactionDraft) async throws -> LedgerTransaction
    func updateTransaction(id: Int, _ draft: TransactionDraft) async throws -> LedgerTransaction
    func deleteTransaction(id: Int) async throws
}

@MainActor
protocol DashboardRepository: AnyObject {
    func dashboardSummary(month: MonthRef) async throws -> DashboardSummary
}

/// Broadcast of "the ledger changed", so screens that did not make the
/// change (Overview, Accounts) refresh when an operation is added, edited or
/// deleted elsewhere.
@MainActor
protocol LedgerEventSource: AnyObject {
    var events: LedgerEvents { get }
}

/// Everything the main tab shell needs.
typealias FinanceRepository = AccountRepository & CategoryRepository & TransactionRepository & DashboardRepository & LedgerEventSource

@MainActor
@Observable
final class LedgerEvents {
    /// Bumped after every successful write. Views observe it with onChange.
    private(set) var revision = 0

    func ledgerDidChange() {
        revision += 1
    }
}

// MARK: - Write models

/// One operation as the editor produces it, independent of storage. Each
/// repository maps it to its own shape (TransactionInput / PATCH body for the
/// server, a SwiftData row on the device).
struct TransactionDraft: Sendable, Hashable {
    var kind: TransactionKind
    var accountID: Int
    /// The selected account's currency as the editor saw it. The server needs
    /// it to state a same-currency edit explicitly; the device store re-reads
    /// it from the account itself.
    var accountCurrency: String
    /// Never set for a transfer.
    var categoryID: Int?
    /// Transfers only.
    var transferAccountID: Int?
    /// What the account was debited (expense/transfer) or credited (income),
    /// in the account's own currency. Always positive.
    var amount: Decimal
    /// The operation's own currency when it differs from the account's;
    /// nil = the account's currency.
    var foreignCurrency: String?
    /// The amount in `foreignCurrency`; only with `foreignCurrency`.
    var foreignAmount: Decimal?
    /// Cross-currency transfers only: what the destination was credited, in
    /// its own currency. nil for a same-currency transfer (= amount).
    var transferAmount: Decimal?
    var description: String
    /// "YYYY-MM-DD"
    var date: String
}

struct AccountInput: Sendable, Hashable {
    var name: String
    /// backend AccountType raw value ("checking", "cash", …).
    var type: String
    var currency: String
    var color: String?
    var isArchived: Bool
    /// Ignored when the repository does not support it.
    var initialBalance: Decimal
}

/// The account types the backend accepts (backend/app/models/enums.py).
enum AccountKind: String, CaseIterable, Identifiable, Sendable {
    case checking
    case debitCard = "debit_card"
    case savings
    case creditCard = "credit_card"
    case cash
    case investment
    case other

    var id: String { rawValue }
}

// MARK: - Errors

/// Failures of the on-device store and of the shared validation rules. The
/// server reports the same rules as APIError.validation.
enum LedgerError: Error, Sendable, Equatable {
    case accountNotFound
    case categoryNotFound
    case transactionNotFound
    case invalid(String)
    case storage(String)
}

extension LedgerError: LocalizedError {
    var errorDescription: String? {
        switch self {
        case .accountNotFound:
            return L10n.text("ledger.error.account")
        case .categoryNotFound:
            return L10n.text("ledger.error.category")
        case .transactionNotFound:
            return L10n.text("ledger.error.transaction")
        case .invalid(let message):
            return message
        case .storage(let detail):
            return L10n.format("ledger.error.storage", detail)
        }
    }
}
