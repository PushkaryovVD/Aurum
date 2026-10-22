import Foundation

// JSON shape of an Aurum backup file — the server's BackupPayload
// (backend/app/schemas/backup.py, format version 2), limited to the parts the
// on-device ledger has: accounts, categories, transactions, app settings.
//
// Keys are spelled out (snake_case) instead of using a key strategy, so the
// file format is visible here line by line. Decoding is lenient in the same
// places the server's is (fields added in later server versions are
// optional); encoding writes every key the server requires, including the
// ones that must be an explicit JSON null.

struct BackupAccountRow: Codable, Sendable {
    let id: Int
    let name: String
    let type: String
    let currency: String
    let color: String?
    let isArchived: Bool

    private enum CodingKeys: String, CodingKey {
        case id, name, type, currency, color
        case isArchived = "is_archived"
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(name, forKey: .name)
        try container.encode(type, forKey: .type)
        try container.encode(currency, forKey: .currency)
        try container.encode(color, forKey: .color)
        try container.encode(isArchived, forKey: .isArchived)
    }
}

struct BackupCategoryRow: Codable, Sendable {
    let id: Int
    let name: String
    let kind: String
    let icon: String?
    let color: String
    let sortOrder: Int
    let isDefault: Bool
    let parentId: Int?

    private enum CodingKeys: String, CodingKey {
        case id, name, kind, icon, color
        case sortOrder = "sort_order"
        case isDefault = "is_default"
        case parentId = "parent_id"
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(name, forKey: .name)
        try container.encode(kind, forKey: .kind)
        try container.encode(icon, forKey: .icon)
        try container.encode(color, forKey: .color)
        try container.encode(sortOrder, forKey: .sortOrder)
        try container.encode(isDefault, forKey: .isDefault)
        try container.encode(parentId, forKey: .parentId)
    }
}

struct BackupTransactionRow: Codable, Sendable {
    let id: Int
    let accountId: Int
    let categoryId: Int?
    let transferAccountId: Int?
    let type: String
    let amount: APIDecimal
    /// Optional on import: absent in backups made before transaction-level
    /// currency existed (then `originalCurrency` / the account currency).
    let currency: String?
    let transactionAmount: APIDecimal?
    /// Legacy pair, read on import only (the server never writes them now).
    let originalAmount: APIDecimal?
    let originalCurrency: String?
    let transferAmount: APIDecimal?
    let purpose: String?
    let description: String
    let merchant: String?
    let notes: String?
    /// "YYYY-MM-DD"
    let date: String
    let tagIds: [Int]?

    private enum CodingKeys: String, CodingKey {
        case id, type, amount, currency, purpose, description, merchant, notes, date
        case accountId = "account_id"
        case categoryId = "category_id"
        case transferAccountId = "transfer_account_id"
        case transactionAmount = "transaction_amount"
        case originalAmount = "original_amount"
        case originalCurrency = "original_currency"
        case transferAmount = "transfer_amount"
        case tagIds = "tag_ids"
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(accountId, forKey: .accountId)
        // Required-but-nullable keys on the server: written as null.
        try container.encode(categoryId, forKey: .categoryId)
        try container.encode(transferAccountId, forKey: .transferAccountId)
        try container.encode(type, forKey: .type)
        try container.encode(amount, forKey: .amount)
        try container.encodeIfPresent(currency, forKey: .currency)
        try container.encodeIfPresent(transactionAmount, forKey: .transactionAmount)
        try container.encode(transferAmount, forKey: .transferAmount)
        try container.encodeIfPresent(purpose, forKey: .purpose)
        try container.encode(description, forKey: .description)
        try container.encode(merchant, forKey: .merchant)
        try container.encode(notes, forKey: .notes)
        try container.encode(date, forKey: .date)
        try container.encode(tagIds ?? [], forKey: .tagIds)
        // original_* are import-only and never written.
    }
}

struct BackupSplitRow: Decodable, Sendable {
    let id: Int
    let transactionId: Int
    let categoryId: Int?
    let amount: APIDecimal

    private enum CodingKeys: String, CodingKey {
        case id, amount
        case transactionId = "transaction_id"
        case categoryId = "category_id"
    }
}

struct BackupSettingsRow: Codable, Sendable {
    let currency: String
}

/// Any row of a section the device ledger does not have yet (assets,
/// budgets, goals, …): accepted and counted, never interpreted.
struct BackupIgnoredRow: Decodable, Sendable {
    init(from decoder: any Decoder) throws {}
}

/// What the app writes.
struct BackupExportFile: Encodable, Sendable {
    let aurumBackupVersion: Int
    let exportedAt: String
    let appVersion: String
    let accounts: [BackupAccountRow]
    let categories: [BackupCategoryRow]
    let transactions: [BackupTransactionRow]
    let appSettings: BackupSettingsRow

    private enum CodingKeys: String, CodingKey {
        case accounts, categories, transactions, tags, assets
        case aurumBackupVersion = "aurum_backup_version"
        case exportedAt = "exported_at"
        case appVersion = "app_version"
        case assetValuations = "asset_valuations"
        case appSettings = "app_settings"
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(aurumBackupVersion, forKey: .aurumBackupVersion)
        try container.encode(exportedAt, forKey: .exportedAt)
        try container.encode(appVersion, forKey: .appVersion)
        try container.encode(accounts, forKey: .accounts)
        try container.encode(categories, forKey: .categories)
        try container.encode([Int](), forKey: .tags)
        try container.encode(transactions, forKey: .transactions)
        // `assets` and `asset_valuations` have no default on the server, so
        // they are present (and empty) even though the device has neither.
        try container.encode([Int](), forKey: .assets)
        try container.encode([Int](), forKey: .assetValuations)
        try container.encode(appSettings, forKey: .appSettings)
    }
}

/// What the app reads — a server export or its own.
struct BackupImportFile: Decodable, Sendable {
    let aurumBackupVersion: Int
    let exportedAt: String?
    let appVersion: String?
    let accounts: [BackupAccountRow]
    let categories: [BackupCategoryRow]
    let transactions: [BackupTransactionRow]
    let transactionSplits: [BackupSplitRow]?
    let appSettings: BackupSettingsRow?

    // Sections that are counted but not imported.
    let tags: [BackupIgnoredRow]?
    let assets: [BackupIgnoredRow]?
    let assetValuations: [BackupIgnoredRow]?
    let budgets: [BackupIgnoredRow]?
    let goals: [BackupIgnoredRow]?
    let goalContributions: [BackupIgnoredRow]?
    let recurringTransactions: [BackupIgnoredRow]?
    let cryptoPortfolios: [BackupIgnoredRow]?
    let cryptoHoldings: [BackupIgnoredRow]?
    let cryptoTransactions: [BackupIgnoredRow]?
    let investmentPortfolios: [BackupIgnoredRow]?
    let securities: [BackupIgnoredRow]?
    let securityTrades: [BackupIgnoredRow]?
    let securityDividends: [BackupIgnoredRow]?
    let securityPrices: [BackupIgnoredRow]?
    let exchangeRates: [BackupIgnoredRow]?

    private enum CodingKeys: String, CodingKey {
        case accounts, categories, transactions, tags, assets, budgets, goals, securities
        case aurumBackupVersion = "aurum_backup_version"
        case exportedAt = "exported_at"
        case appVersion = "app_version"
        case transactionSplits = "transaction_splits"
        case appSettings = "app_settings"
        case assetValuations = "asset_valuations"
        case goalContributions = "goal_contributions"
        case recurringTransactions = "recurring_transactions"
        case cryptoPortfolios = "crypto_portfolios"
        case cryptoHoldings = "crypto_holdings"
        case cryptoTransactions = "crypto_transactions"
        case investmentPortfolios = "investment_portfolios"
        case securityTrades = "security_trades"
        case securityDividends = "security_dividends"
        case securityPrices = "security_prices"
        case exchangeRates = "exchange_rates"
    }

    /// Rows of every section the device does not import. Tags are reported
    /// separately (per operation) by BackupCodec: the operations themselves
    /// are imported, only their labels are lost.
    var ignoredRecordCount: Int {
        let sections: [[BackupIgnoredRow]?] = [
            assets, assetValuations, budgets, goals, goalContributions, recurringTransactions,
            cryptoPortfolios, cryptoHoldings, cryptoTransactions, investmentPortfolios,
            securities, securityTrades, securityDividends, securityPrices, exchangeRates,
        ]
        return sections.reduce(0) { $0 + ($1?.count ?? 0) }
    }
}
