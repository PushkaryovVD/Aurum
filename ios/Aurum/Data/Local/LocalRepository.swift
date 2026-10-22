import Foundation
import Observation
import SwiftData

/// "Only on iPhone" mode: the whole ledger lives in a SwiftData store on the
/// device (LocalStore). No network is involved at any point.
///
/// Reads fetch the rows, convert them to plain values and hand them to the
/// pure LedgerMath / LedgerRules — the same rules the server applies — so
/// this type is only persistence and mapping. Everything runs on the main
/// actor with the container's mainContext; the data set of one person's
/// ledger is small enough that in-memory filtering is simpler and safer than
/// SwiftData predicates.
@MainActor
@Observable
final class LocalRepository: FinanceRepository {
    let events: LedgerEvents
    /// What the Overview reports in; cached from LocalSettings.
    private(set) var reportingCurrency: String

    private let container: ModelContainer

    private var context: ModelContext { container.mainContext }

    init(container: ModelContainer) throws {
        self.container = container
        self.events = LedgerEvents()
        self.reportingCurrency = Self.defaultReportingCurrency
        reportingCurrency = try prepareStore()
    }

    // MARK: - Accounts

    var supportsInitialBalance: Bool { true }

    func accounts(includeArchived: Bool) async throws -> [AccountWithBalance] {
        LedgerMath.accountsWithBalance(
            accounts: try accountValues(),
            entries: try entryValues(),
            includeArchived: includeArchived
        )
    }

    func createAccount(_ input: AccountInput) async throws -> AccountWithBalance {
        let checked = try Self.checkedAccount(input)
        let rows = try fetchAccounts()
        let id = (rows.map(\.ledgerID).max() ?? 0) + 1
        context.insert(
            LocalAccount(
                ledgerID: id,
                name: checked.name,
                typeRaw: checked.type,
                currency: checked.currency,
                colorHex: checked.color,
                isArchived: checked.isArchived,
                initialBalanceRaw: DecimalParsing.wireString(checked.initialBalance),
                createdAt: Date()
            )
        )
        try commit()
        return try account(id: id)
    }

    func updateAccount(id: Int, _ input: AccountInput) async throws -> AccountWithBalance {
        let checked = try Self.checkedAccount(input)
        guard let row = try fetchAccounts().first(where: { $0.ledgerID == id }) else {
            throw LedgerError.accountNotFound
        }
        if checked.currency != row.currency.uppercased() {
            // Same rule as the server: the history is recorded in the old
            // currency, so relabelling it would silently change its meaning.
            let used = try fetchTransactions().contains { $0.accountID == id || $0.transferAccountID == id }
            if used {
                throw LedgerError.invalid(L10n.text("account.error.currencyLocked"))
            }
        }
        row.name = checked.name
        row.typeRaw = checked.type
        row.currency = checked.currency
        row.colorHex = checked.color
        row.isArchived = checked.isArchived
        row.initialBalanceRaw = DecimalParsing.wireString(checked.initialBalance)
        try commit()
        return try account(id: id)
    }

    // MARK: - Categories

    func categories() async throws -> [LedgerCategory] {
        try categoryValues()
    }

    // MARK: - Transactions

    func transactions(_ filter: TransactionFilter, page: Int, pageSize: Int) async throws -> TransactionPage {
        let accounts = try accountValues()
        let categories = try categoryValues()
        let result = LedgerMath.page(try entryValues(), filter: filter, page: page, pageSize: pageSize)
        let items = result.items.map { Self.transaction($0, accounts: accounts, categories: categories) }
        return TransactionPage(items: items, total: result.total, page: page, pageSize: pageSize)
    }

    func createTransaction(_ draft: TransactionDraft) async throws -> LedgerTransaction {
        let resolved = try resolve(draft)
        let id = (try fetchTransactions().map(\.ledgerID).max() ?? 0) + 1
        let now = Date()
        context.insert(
            LocalTransaction(
                ledgerID: id,
                accountID: resolved.accountID,
                categoryID: resolved.categoryID,
                transferAccountID: resolved.transferAccountID,
                typeRaw: resolved.type,
                amountRaw: DecimalParsing.wireString(resolved.amount),
                currency: resolved.currency,
                transactionAmountRaw: DecimalParsing.wireString(resolved.transactionAmount),
                transferAmountRaw: resolved.transferAmount.map { DecimalParsing.wireString($0) },
                purposeRaw: "ordinary",
                descriptionText: resolved.description,
                merchant: nil,
                notes: nil,
                day: resolved.date,
                createdAt: now,
                updatedAt: now
            )
        )
        try commit()
        return try transaction(id: id)
    }

    func updateTransaction(id: Int, _ draft: TransactionDraft) async throws -> LedgerTransaction {
        let resolved = try resolve(draft)
        guard let row = try fetchTransactions().first(where: { $0.ledgerID == id }) else {
            throw LedgerError.transactionNotFound
        }
        row.accountID = resolved.accountID
        row.categoryID = resolved.categoryID
        row.transferAccountID = resolved.transferAccountID
        row.typeRaw = resolved.type
        row.amountRaw = DecimalParsing.wireString(resolved.amount)
        row.currency = resolved.currency
        row.transactionAmountRaw = DecimalParsing.wireString(resolved.transactionAmount)
        row.transferAmountRaw = resolved.transferAmount.map { DecimalParsing.wireString($0) }
        row.descriptionText = resolved.description
        row.day = resolved.date
        row.updatedAt = Date()
        // purpose, merchant and notes are not edited by the app and stay as
        // they were (they may have come from a server backup).
        try commit()
        return try transaction(id: id)
    }

    func deleteTransaction(id: Int) async throws {
        guard let row = try fetchTransactions().first(where: { $0.ledgerID == id }) else {
            throw LedgerError.transactionNotFound
        }
        context.delete(row)
        try commit()
    }

    // MARK: - Dashboard

    func dashboardSummary(month: MonthRef) async throws -> DashboardSummary {
        LedgerMath.dashboardSummary(
            month: month,
            accounts: try accountValues(),
            categories: try categoryValues(),
            entries: try entryValues(),
            reportingCurrency: reportingCurrency,
            otherName: "Other"
        )
    }

    // MARK: - Settings

    func setReportingCurrency(_ code: String) throws {
        let normalized = code.trimmingCharacters(in: .whitespaces).uppercased()
        guard Self.isCurrencyCode(normalized) else {
            throw LedgerError.invalid(L10n.text("add.error.currency"))
        }
        let settings = try settingsRow()
        settings.reportingCurrency = normalized
        try commit()
        reportingCurrency = normalized
    }

    // MARK: - Backup

    /// The whole ledger as values, for export.
    func snapshot() throws -> LedgerSnapshot {
        LedgerSnapshot(
            accounts: try accountValues(),
            categories: try categoryValues(),
            entries: try entryValues(),
            reportingCurrency: reportingCurrency
        )
    }

    /// Replaces everything with `snapshot` in a single save: either the
    /// whole backup is stored or (on any failure) nothing changed.
    /// The snapshot must already be validated (BackupCodec does that).
    func replaceAll(with snapshot: LedgerSnapshot) throws {
        for row in try fetchTransactions() { context.delete(row) }
        for row in try fetchCategories() { context.delete(row) }
        for row in try fetchAccounts() { context.delete(row) }

        let now = Date()
        for account in snapshot.accounts {
            context.insert(
                LocalAccount(
                    ledgerID: account.id,
                    name: account.name,
                    typeRaw: account.type,
                    currency: account.currency.uppercased(),
                    colorHex: account.color,
                    isArchived: account.isArchived,
                    initialBalanceRaw: DecimalParsing.wireString(account.initialBalance),
                    createdAt: now
                )
            )
        }
        for category in snapshot.categories {
            context.insert(
                LocalCategory(
                    ledgerID: category.id,
                    name: category.name,
                    kindRaw: category.kind,
                    icon: category.icon,
                    colorHex: category.color,
                    sortOrder: category.sortOrder,
                    isDefault: category.isDefault,
                    parentID: category.parentId
                )
            )
        }
        for entry in snapshot.entries {
            context.insert(
                LocalTransaction(
                    ledgerID: entry.id,
                    accountID: entry.accountID,
                    categoryID: entry.categoryID,
                    transferAccountID: entry.transferAccountID,
                    typeRaw: entry.type,
                    amountRaw: DecimalParsing.wireString(entry.amount),
                    currency: entry.currency.uppercased(),
                    transactionAmountRaw: DecimalParsing.wireString(entry.transactionAmount),
                    transferAmountRaw: entry.transferAmount.map { DecimalParsing.wireString($0) },
                    purposeRaw: entry.purpose,
                    descriptionText: entry.description,
                    merchant: entry.merchant,
                    notes: entry.notes,
                    day: entry.date,
                    createdAt: now,
                    updatedAt: now
                )
            )
        }
        let settings = try settingsRow()
        settings.reportingCurrency = snapshot.reportingCurrency.uppercased()
        // An imported ledger is the user's data: the defaults must not be
        // re-seeded into it later.
        settings.didSeedDefaults = true
        do {
            try context.save()
        } catch {
            // Restores every deleted row and drops every inserted one.
            context.rollback()
            throw LedgerError.storage(error.localizedDescription)
        }
        reportingCurrency = snapshot.reportingCurrency.uppercased()
        // Every screen reloads on this, exactly as after a single edit.
        events.ledgerDidChange()
    }

    // MARK: - Store preparation

    /// Creates the settings row and, once, the server's default categories
    /// and starter account. Returns the reporting currency.
    private func prepareStore() throws -> String {
        let settings: LocalSettings
        if let existing = try context.fetch(FetchDescriptor<LocalSettings>()).first {
            settings = existing
        } else {
            settings = LocalSettings(reportingCurrency: Self.defaultReportingCurrency, didSeedDefaults: false)
            context.insert(settings)
        }
        if !settings.didSeedDefaults {
            if try fetchCategories().isEmpty {
                for (index, seed) in DefaultCategories.all.enumerated() {
                    context.insert(
                        LocalCategory(
                            ledgerID: index + 1,
                            name: seed.name,
                            kindRaw: seed.kind,
                            icon: seed.icon,
                            colorHex: seed.color,
                            sortOrder: index,
                            isDefault: true,
                            parentID: nil
                        )
                    )
                }
            }
            if try fetchAccounts().isEmpty {
                context.insert(
                    LocalAccount(
                        ledgerID: 1,
                        name: L10n.text("local.starterAccount"),
                        typeRaw: DefaultCategories.starterAccountType,
                        currency: settings.reportingCurrency,
                        colorHex: DefaultCategories.starterAccountColor,
                        isArchived: false,
                        initialBalanceRaw: "0",
                        createdAt: Date()
                    )
                )
            }
            settings.didSeedDefaults = true
        }
        if context.hasChanges {
            do {
                try context.save()
            } catch {
                context.rollback()
                throw LedgerError.storage(error.localizedDescription)
            }
        }
        return settings.reportingCurrency
    }

    // MARK: - Fetching

    private func fetchAccounts() throws -> [LocalAccount] {
        try context.fetch(FetchDescriptor<LocalAccount>())
    }

    private func fetchCategories() throws -> [LocalCategory] {
        try context.fetch(FetchDescriptor<LocalCategory>())
    }

    private func fetchTransactions() throws -> [LocalTransaction] {
        try context.fetch(FetchDescriptor<LocalTransaction>())
    }

    private func settingsRow() throws -> LocalSettings {
        if let existing = try context.fetch(FetchDescriptor<LocalSettings>()).first {
            return existing
        }
        let created = LocalSettings(reportingCurrency: reportingCurrency, didSeedDefaults: true)
        context.insert(created)
        return created
    }

    private func commit() throws {
        do {
            try context.save()
        } catch {
            context.rollback()
            throw LedgerError.storage(error.localizedDescription)
        }
        events.ledgerDidChange()
    }

    // MARK: - Mapping (rows -> values)

    private func accountValues() throws -> [AccountValue] {
        try fetchAccounts().map { row in
            AccountValue(
                id: row.ledgerID,
                name: row.name,
                type: row.typeRaw,
                currency: row.currency.uppercased(),
                color: row.colorHex,
                isArchived: row.isArchived,
                initialBalance: DecimalParsing.parseWire(row.initialBalanceRaw) ?? 0
            )
        }
    }

    private func categoryValues() throws -> [LedgerCategory] {
        try fetchCategories()
            .map { row in
                LedgerCategory(
                    id: row.ledgerID,
                    name: row.name,
                    kind: row.kindRaw,
                    icon: row.icon,
                    color: row.colorHex,
                    sortOrder: row.sortOrder,
                    isDefault: row.isDefault,
                    parentId: row.parentID
                )
            }
            .sorted { lhs, rhs in
                lhs.sortOrder == rhs.sortOrder ? lhs.id < rhs.id : lhs.sortOrder < rhs.sortOrder
            }
    }

    private func entryValues() throws -> [EntryValue] {
        try fetchTransactions().map { row in
            let amount = DecimalParsing.parseWire(row.amountRaw) ?? 0
            return EntryValue(
                id: row.ledgerID,
                accountID: row.accountID,
                categoryID: row.categoryID,
                transferAccountID: row.transferAccountID,
                type: row.typeRaw,
                amount: amount,
                currency: row.currency,
                transactionAmount: DecimalParsing.parseWire(row.transactionAmountRaw) ?? amount,
                transferAmount: row.transferAmountRaw.flatMap { DecimalParsing.parseWire($0) },
                purpose: row.purposeRaw,
                description: row.descriptionText,
                merchant: row.merchant,
                notes: row.notes,
                date: row.day
            )
        }
    }

    private func resolve(_ draft: TransactionDraft) throws -> LedgerRules.Resolved {
        switch LedgerRules.resolve(draft, accounts: try accountValues(), categories: try categoryValues()) {
        case .success(let resolved):
            return resolved
        case .failure(let error):
            throw error
        }
    }

    private func account(id: Int) throws -> AccountWithBalance {
        let all = LedgerMath.accountsWithBalance(
            accounts: try accountValues(),
            entries: try entryValues(),
            includeArchived: true
        )
        guard let account = all.first(where: { $0.id == id }) else {
            throw LedgerError.accountNotFound
        }
        return account
    }

    private func transaction(id: Int) throws -> LedgerTransaction {
        guard let entry = try entryValues().first(where: { $0.id == id }) else {
            throw LedgerError.transactionNotFound
        }
        return Self.transaction(entry, accounts: try accountValues(), categories: try categoryValues())
    }

    /// The same shape the server returns, so every screen renders both modes
    /// identically. Rows with a missing account (should not happen: imports
    /// are checked) still render, under a placeholder, instead of vanishing.
    private static func transaction(
        _ entry: EntryValue,
        accounts: [AccountValue],
        categories: [LedgerCategory]
    ) -> LedgerTransaction {
        let account = accounts.first { $0.id == entry.accountID }
        let reference = AccountRef(
            id: entry.accountID,
            name: account?.name ?? "?",
            type: account?.type ?? AccountKind.other.rawValue,
            currency: account?.currency ?? entry.currency,
            color: account?.color,
            isArchived: account?.isArchived ?? false
        )
        let category = entry.categoryID.flatMap { id in categories.first { $0.id == id } }
        return LedgerTransaction(
            id: entry.id,
            accountId: entry.accountID,
            categoryId: entry.categoryID,
            transferAccountId: entry.transferAccountID,
            type: entry.type,
            amount: APIDecimal(entry.amount),
            currency: entry.currency,
            transactionAmount: APIDecimal(entry.transactionAmount),
            exchangeRateToKzt: nil,
            baseAmountKzt: nil,
            exchangeRateSource: nil,
            transferAmount: entry.transferAmount.map { APIDecimal($0) },
            purpose: entry.purpose,
            description: entry.description,
            merchant: entry.merchant,
            notes: entry.notes,
            date: entry.date,
            account: reference,
            category: category,
            tags: [],
            splits: []
        )
    }

    // MARK: - Validation

    private static func checkedAccount(_ input: AccountInput) throws -> AccountInput {
        let name = String(input.name.trimmingCharacters(in: .whitespacesAndNewlines).prefix(100))
        guard !name.isEmpty else {
            throw LedgerError.invalid(L10n.text("account.error.name"))
        }
        let currency = input.currency.trimmingCharacters(in: .whitespaces).uppercased()
        guard isCurrencyCode(currency) else {
            throw LedgerError.invalid(L10n.text("add.error.currency"))
        }
        let type = AccountKind(rawValue: input.type)?.rawValue ?? AccountKind.other.rawValue
        return AccountInput(
            name: name,
            type: type,
            currency: currency,
            color: input.color,
            isArchived: input.isArchived,
            initialBalance: input.initialBalance
        )
    }

    nonisolated static func isCurrencyCode(_ code: String) -> Bool {
        code.count == 3 && code.unicodeScalars.allSatisfy { $0.isASCII && CharacterSet.uppercaseLetters.contains($0) }
    }

    /// The device region's currency, or USD (the server's own fallback).
    nonisolated static var defaultReportingCurrency: String {
        let code = Locale.current.currency?.identifier.uppercased() ?? "USD"
        return isCurrencyCode(code) ? code : "USD"
    }
}
