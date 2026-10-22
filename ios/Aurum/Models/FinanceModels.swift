import Foundation

// Mirrors the read shapes in frontend/src/types/index.ts. Enumerations the
// backend may extend (account type, transaction type, …) stay raw strings so
// a new server-side value never breaks decoding of a whole list.

/// The account as nested inside a Transaction (no live balance).
struct AccountRef: Decodable, Sendable, Hashable, Identifiable {
    let id: Int
    let name: String
    let type: String
    let currency: String
    let color: String?
    let isArchived: Bool
}

/// GET /api/accounts — the account plus its live balance.
struct AccountWithBalance: Decodable, Sendable, Hashable, Identifiable {
    let id: Int
    let name: String
    let type: String
    let currency: String
    let color: String?
    let isArchived: Bool
    /// In the account's own currency.
    let balance: APIDecimal
    let transactionCount: Int?
    /// On-device mode only: the money the account held before its first
    /// recorded operation (already included in `balance`). The server has no
    /// such field, so it decodes as nil there.
    let initialBalance: APIDecimal?
}

/// GET /api/categories (named LedgerCategory: `Category` is also an
/// Objective-C runtime typealias, best not shadowed).
struct LedgerCategory: Decodable, Sendable, Hashable, Identifiable {
    let id: Int
    let name: String
    /// "income" | "expense"
    let kind: String
    let icon: String?
    let color: String
    let sortOrder: Int
    let isDefault: Bool
    let parentId: Int?
}

struct Tag: Decodable, Sendable, Hashable, Identifiable {
    let id: Int
    let name: String
}

struct TransactionSplit: Decodable, Sendable, Hashable, Identifiable {
    let id: Int
    let categoryId: Int?
    let category: LedgerCategory?
    let amount: APIDecimal
    let note: String?
}

enum TransactionKind: String, Sendable, CaseIterable, Identifiable {
    case expense
    case income
    case transfer

    var id: String { rawValue }
}

// Named LedgerTransaction rather than Transaction so it can never be confused
// with SwiftUI.Transaction (the animation transaction) in view files.
struct LedgerTransaction: Decodable, Sendable, Hashable, Identifiable {
    let id: Int
    let accountId: Int
    let categoryId: Int?
    let transferAccountId: Int?
    /// "income" | "expense" | "transfer"
    let type: String
    /// What the account was actually debited, in the account's own currency.
    let amount: APIDecimal
    /// The transaction's own currency and the amount in it.
    let currency: String
    let transactionAmount: APIDecimal
    let exchangeRateToKzt: APIDecimal?
    let baseAmountKzt: APIDecimal?
    let exchangeRateSource: String?
    let transferAmount: APIDecimal?
    let purpose: String?
    let description: String
    let merchant: String?
    let notes: String?
    /// "YYYY-MM-DD"
    let date: String
    let account: AccountRef
    let category: LedgerCategory?
    let tags: [Tag]
    let splits: [TransactionSplit]

    var kind: TransactionKind? { TransactionKind(rawValue: type) }

    /// True when the row was paid in a currency other than its account's.
    var isForeignCurrency: Bool {
        currency.uppercased() != account.currency.uppercased()
    }
}

/// GET /api/transactions
struct TransactionPage: Decodable, Sendable {
    let items: [LedgerTransaction]
    let total: Int
    let page: Int
    let pageSize: Int
}

/// Body of POST /api/transactions — the subset of the web client's
/// TransactionInput this app writes. Optional fields left nil are omitted
/// from the JSON entirely, which the backend reads as "use the default"
/// (account currency, transaction_amount = amount, no tags, no splits).
struct TransactionInput: Encodable, Sendable {
    let accountId: Int
    let categoryId: Int?
    let transferAccountId: Int?
    let type: String
    /// Debit in the account's currency.
    let amount: APIDecimal
    /// Only for a genuinely foreign-currency transaction.
    let currency: String?
    let transactionAmount: APIDecimal?
    /// Transfers only: what the destination account was credited, in its own
    /// currency (equal to `amount` for a same-currency transfer).
    let transferAmount: APIDecimal?
    let description: String
    let notes: String?
    /// "YYYY-MM-DD"
    let date: String
    let tagIds: [Int]
}

// MARK: - Dashboard

struct CategoryBreakdownChildItem: Decodable, Sendable, Hashable {
    let categoryId: Int
    let name: String
    let color: String
    let icon: String?
    let amount: APIDecimal
}

struct CategoryBreakdownItem: Decodable, Sendable, Hashable {
    let categoryId: Int?
    let name: String
    let color: String
    let icon: String?
    let amount: APIDecimal
    let percent: Double
    let children: [CategoryBreakdownChildItem]?
}

struct CurrencyBalance: Decodable, Sendable, Hashable {
    let currency: String
    let amount: APIDecimal
    /// nil when no exchange rate was available — must be shown as such, not
    /// as if the foreign balance were already in the reporting currency.
    let amountReporting: APIDecimal?
    let rateToKzt: APIDecimal?
    let rateDate: String?
}

struct BalanceSummary: Decodable, Sendable, Hashable {
    let reportingCurrency: String
    let total: APIDecimal
    /// True when at least one currency had no usable rate — `total` then
    /// covers only the currencies that did convert.
    let incomplete: Bool
    let items: [CurrencyBalance]
}

/// GET /api/dashboard/summary?year=&month=
struct DashboardSummary: Decodable, Sendable {
    let year: Int
    let month: Int
    let realIncome: APIDecimal
    let spent: APIDecimal
    let net: APIDecimal
    let transferredOut: APIDecimal?
    let spendingByCategory: [CategoryBreakdownItem]
    /// All-time rather than month-scoped: the money currently in the accounts.
    let balance: BalanceSummary
    /// On-device mode only: account currencies whose operations could not be
    /// counted in the month's income/spending because the device has no
    /// exchange rate for them (the server's analogue is a row without a KZT
    /// snapshot, which it also leaves out). nil/empty = nothing left out.
    let excludedCurrencies: [String]?
}
