import Foundation

/// The whole on-device ledger as plain values: what a backup is made from
/// and what an import replaces the store with. Later stages add their own
/// arrays here (budgets, goals, recurring payments, assets).
struct LedgerSnapshot: Sendable, Hashable {
    var accounts: [AccountValue]
    var categories: [LedgerCategory]
    var entries: [EntryValue]
    var reportingCurrency: String
}
