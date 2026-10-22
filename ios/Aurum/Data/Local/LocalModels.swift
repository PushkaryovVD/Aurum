import Foundation
import SwiftData

// SwiftData schema of the on-device ledger ("Only on iPhone" mode).
//
// Deliberate choices, all in favour of exactness and of a 1:1 mapping onto
// the server's backup format:
// - Money is stored as the canonical decimal string ("2650.5"), never as
//   Double or a SwiftData-encoded Decimal, so it round-trips bit-exactly.
// - Dates of operations are calendar days ("YYYY-MM-DD"), like the server.
// - Every row has an integer `ledgerID`, the same kind of id the server
//   uses, so the DTOs in Models/ are reused as-is and a backup keeps its
//   references. Links between rows are plain ids (no SwiftData
//   relationships): referential rules are applied by LocalRepository, the
//   way the server's foreign keys do it. `ledgerID` is unique by
//   construction (LocalRepository allocates max + 1; a backup is checked for
//   duplicates before import) rather than by `@Attribute(.unique)`, whose
//   upsert-on-conflict would make "delete everything, insert the backup" in
//   one save ambiguous.
// - Enumerations are raw strings with the backend's values.
//
// @Model classes are not Sendable: they are only touched on the main actor,
// through the container's mainContext (see LocalStore). Conversion to the
// Sendable value types happens in LocalRepository.
//
// Adding a later area (budgets, goals, recurring payments, assets) = a new
// @Model here, listed in LocalStore.schema, plus its repository methods.

@Model
final class LocalAccount {
    var ledgerID: Int
    var name: String
    /// backend AccountType raw value.
    var typeRaw: String
    /// ISO 4217, upper case.
    var currency: String
    /// "#RRGGBB" or nil.
    var colorHex: String?
    var isArchived: Bool
    /// Decimal string, in `currency`; "0" when none.
    var initialBalanceRaw: String
    var createdAt: Date

    init(
        ledgerID: Int,
        name: String,
        typeRaw: String,
        currency: String,
        colorHex: String?,
        isArchived: Bool,
        initialBalanceRaw: String,
        createdAt: Date
    ) {
        self.ledgerID = ledgerID
        self.name = name
        self.typeRaw = typeRaw
        self.currency = currency
        self.colorHex = colorHex
        self.isArchived = isArchived
        self.initialBalanceRaw = initialBalanceRaw
        self.createdAt = createdAt
    }
}

@Model
final class LocalCategory {
    var ledgerID: Int
    /// Seeded defaults keep the server's English name (so a backup matches
    /// the server's own defaults); the UI translates them (CategoryNames).
    var name: String
    /// "income" | "expense"
    var kindRaw: String
    /// Lucide icon name, as on the server (not drawn by the iOS app).
    var icon: String?
    var colorHex: String
    var sortOrder: Int
    var isDefault: Bool
    /// One level deep only, as on the server.
    var parentID: Int?

    init(
        ledgerID: Int,
        name: String,
        kindRaw: String,
        icon: String?,
        colorHex: String,
        sortOrder: Int,
        isDefault: Bool,
        parentID: Int?
    ) {
        self.ledgerID = ledgerID
        self.name = name
        self.kindRaw = kindRaw
        self.icon = icon
        self.colorHex = colorHex
        self.sortOrder = sortOrder
        self.isDefault = isDefault
        self.parentID = parentID
    }
}

@Model
final class LocalTransaction {
    var ledgerID: Int
    var accountID: Int
    var categoryID: Int?
    var transferAccountID: Int?
    /// "income" | "expense" | "transfer"
    var typeRaw: String
    /// Decimal string, positive, in the account's currency.
    var amountRaw: String
    /// The operation's own currency and the amount in it.
    var currency: String
    var transactionAmountRaw: String
    /// Transfers: credited to the destination, in its currency.
    var transferAmountRaw: String?
    /// backend TransactionPurpose raw value ("ordinary" unless imported).
    var purposeRaw: String
    var descriptionText: String
    var merchant: String?
    var notes: String?
    /// "YYYY-MM-DD"
    var day: String
    var createdAt: Date
    var updatedAt: Date

    init(
        ledgerID: Int,
        accountID: Int,
        categoryID: Int?,
        transferAccountID: Int?,
        typeRaw: String,
        amountRaw: String,
        currency: String,
        transactionAmountRaw: String,
        transferAmountRaw: String?,
        purposeRaw: String,
        descriptionText: String,
        merchant: String?,
        notes: String?,
        day: String,
        createdAt: Date,
        updatedAt: Date
    ) {
        self.ledgerID = ledgerID
        self.accountID = accountID
        self.categoryID = categoryID
        self.transferAccountID = transferAccountID
        self.typeRaw = typeRaw
        self.amountRaw = amountRaw
        self.currency = currency
        self.transactionAmountRaw = transactionAmountRaw
        self.transferAmountRaw = transferAmountRaw
        self.purposeRaw = purposeRaw
        self.descriptionText = descriptionText
        self.merchant = merchant
        self.notes = notes
        self.day = day
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}

/// Singleton row with the device ledger's own settings (the server's
/// app_settings). Exactly one exists; LocalRepository creates it.
@Model
final class LocalSettings {
    /// ISO 4217 code the Overview reports in.
    var reportingCurrency: String
    /// Set once the default categories and starter account were created, so
    /// deleting them later never makes them come back.
    var didSeedDefaults: Bool

    init(reportingCurrency: String, didSeedDefaults: Bool) {
        self.reportingCurrency = reportingCurrency
        self.didSeedDefaults = didSeedDefaults
    }
}
