import Foundation

/// Converts between the on-device ledger (LedgerSnapshot) and an Aurum backup
/// file. Pure: no store access — LocalRepository supplies the snapshot and
/// applies the import plan, so this part can be checked on its own.
///
/// Compatibility with the server (backend/app/services/backup_service.py):
/// - export writes format version 2 with accounts, categories, transactions
///   and app_settings.currency; every other section is empty;
/// - import accepts version 1 and 2 files from the server or from this app,
///   with the same reference checks the server runs before restoring, and
///   the same fallbacks for older files (currency / transaction_amount);
/// - the device-only opening balance travels as one marked operation per
///   account (see `openingBalanceMarker`) and is folded back on import.
enum BackupCodec {
    static let formatVersion = 2
    static let supportedVersions: Set<Int> = [1, 2]

    /// Notes of the synthetic operation that carries an account's opening
    /// balance through a server round trip.
    static let openingBalanceMarker = "[aurum-ios:opening-balance]"
    static let openingBalanceDescription = "Opening balance"

    enum CodecError: Error, Sendable, Equatable {
        case unreadable(String)
        case unsupportedVersion(Int)
        case invalid(String)
    }

    /// What an import would do, shown to the user before anything changes.
    struct ImportPlan: Sendable, Hashable {
        let snapshot: LedgerSnapshot
        let exportedAt: String?
        let sourceAppVersion: String?
        let openingBalances: Int
        /// Split operations stored under their (shared) parent category.
        let mergedSplits: Int
        /// Split operations whose lines could not be reduced to one category.
        let uncategorizedSplits: Int
        let operationsWithTags: Int
        /// Rows of sections the device does not have (assets, budgets, …).
        let ignoredRecords: Int
    }

    // MARK: - Export

    static func encode(
        _ snapshot: LedgerSnapshot,
        exportedAt: Date,
        appVersion: String,
        today: String
    ) throws -> Data {
        var rows = snapshot.entries
            .sorted { $0.id < $1.id }
            .map { transactionRow($0) }
        var nextID = (snapshot.entries.map(\.id).max() ?? 0) + 1
        for account in snapshot.accounts.sorted(by: { $0.id < $1.id }) where account.initialBalance != 0 {
            let touching = snapshot.entries.filter { $0.accountID == account.id || $0.transferAccountID == account.id }
            let date = touching.map(\.date).min() ?? today
            let magnitude = account.initialBalance < 0 ? -account.initialBalance : account.initialBalance
            rows.append(
                BackupTransactionRow(
                    id: nextID,
                    accountId: account.id,
                    categoryId: nil,
                    transferAccountId: nil,
                    type: account.initialBalance > 0 ? TransactionKind.income.rawValue : TransactionKind.expense.rawValue,
                    amount: APIDecimal(magnitude),
                    currency: account.currency.uppercased(),
                    transactionAmount: APIDecimal(magnitude),
                    originalAmount: nil,
                    originalCurrency: nil,
                    transferAmount: nil,
                    purpose: "ordinary",
                    description: openingBalanceDescription,
                    merchant: nil,
                    notes: openingBalanceMarker,
                    date: date,
                    tagIds: []
                )
            )
            nextID += 1
        }

        let file = BackupExportFile(
            aurumBackupVersion: formatVersion,
            exportedAt: exportedAt.formatted(.iso8601),
            appVersion: appVersion,
            accounts: snapshot.accounts.sorted { $0.id < $1.id }.map { account in
                BackupAccountRow(
                    id: account.id,
                    name: account.name,
                    type: account.type,
                    currency: account.currency.uppercased(),
                    color: account.color,
                    isArchived: account.isArchived
                )
            },
            categories: snapshot.categories.sorted { $0.id < $1.id }.map { category in
                BackupCategoryRow(
                    id: category.id,
                    name: category.name,
                    kind: category.kind,
                    icon: category.icon,
                    color: category.color,
                    sortOrder: category.sortOrder,
                    isDefault: category.isDefault,
                    parentId: category.parentId
                )
            },
            transactions: rows,
            appSettings: BackupSettingsRow(currency: snapshot.reportingCurrency.uppercased())
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try encoder.encode(file)
    }

    private static func transactionRow(_ entry: EntryValue) -> BackupTransactionRow {
        BackupTransactionRow(
            id: entry.id,
            accountId: entry.accountID,
            categoryId: entry.categoryID,
            transferAccountId: entry.transferAccountID,
            type: entry.type,
            amount: APIDecimal(entry.amount),
            currency: entry.currency.uppercased(),
            transactionAmount: APIDecimal(entry.transactionAmount),
            originalAmount: nil,
            originalCurrency: nil,
            transferAmount: entry.transferAmount.map { APIDecimal($0) },
            purpose: entry.purpose,
            description: entry.description,
            merchant: entry.merchant,
            notes: entry.notes,
            date: entry.date,
            tagIds: []
        )
    }

    // MARK: - Import

    static func decode(_ data: Data, fallbackCurrency: String) -> Result<ImportPlan, CodecError> {
        let file: BackupImportFile
        do {
            file = try JSONDecoder().decode(BackupImportFile.self, from: data)
        } catch {
            return .failure(.unreadable(String(describing: error)))
        }
        guard supportedVersions.contains(file.aurumBackupVersion) else {
            return .failure(.unsupportedVersion(file.aurumBackupVersion))
        }
        do {
            return .success(try plan(for: file, fallbackCurrency: fallbackCurrency))
        } catch let error as CodecError {
            return .failure(error)
        } catch {
            return .failure(.invalid(String(describing: error)))
        }
    }

    private static func plan(for file: BackupImportFile, fallbackCurrency: String) throws -> ImportPlan {
        // Accounts
        var accountIDs = Set<Int>()
        var currencyByAccount: [Int: String] = [:]
        for row in file.accounts {
            guard accountIDs.insert(row.id).inserted else {
                throw CodecError.invalid("Duplicate account id \(row.id)")
            }
            let currency = row.currency.uppercased()
            guard isCurrencyCode(currency) else {
                throw CodecError.invalid("Account \(row.id) has an invalid currency \(row.currency)")
            }
            currencyByAccount[row.id] = currency
        }

        // Categories
        var categoryByID: [Int: BackupCategoryRow] = [:]
        for row in file.categories {
            guard categoryByID[row.id] == nil else {
                throw CodecError.invalid("Duplicate category id \(row.id)")
            }
            guard row.kind == "income" || row.kind == "expense" else {
                throw CodecError.invalid("Category \(row.id) has an unknown kind \(row.kind)")
            }
            categoryByID[row.id] = row
        }
        for row in file.categories {
            if let parent = row.parentId, categoryByID[parent] == nil {
                throw CodecError.invalid("Category \(row.id) references unknown parent_id \(parent)")
            }
        }

        // Split lines, by transaction.
        var splitCategories: [Int: [Int]] = [:]
        for split in file.transactionSplits ?? [] {
            if let category = split.categoryId {
                splitCategories[split.transactionId, default: []].append(category)
            }
        }

        // Transactions
        var transactionIDs = Set<Int>()
        var openingBalance: [Int: Decimal] = [:]
        var openingCount = 0
        var mergedSplits = 0
        var uncategorizedSplits = 0
        var withTags = 0
        var entries: [EntryValue] = []
        let validTypes: Set<String> = ["income", "expense", "transfer"]
        for row in file.transactions {
            guard transactionIDs.insert(row.id).inserted else {
                throw CodecError.invalid("Duplicate transaction id \(row.id)")
            }
            guard let accountCurrency = currencyByAccount[row.accountId] else {
                throw CodecError.invalid("Transaction \(row.id) references unknown account_id \(row.accountId)")
            }
            if let destination = row.transferAccountId, !accountIDs.contains(destination) {
                throw CodecError.invalid("Transaction \(row.id) references unknown transfer_account_id \(destination)")
            }
            if let category = row.categoryId, categoryByID[category] == nil {
                throw CodecError.invalid("Transaction \(row.id) references unknown category_id \(category)")
            }
            guard validTypes.contains(row.type) else {
                throw CodecError.invalid("Transaction \(row.id) has an unknown type \(row.type)")
            }
            guard row.amount.value > 0 else {
                throw CodecError.invalid("Transaction \(row.id) has a non-positive amount")
            }
            guard APIDate.parse(row.date) != nil else {
                throw CodecError.invalid("Transaction \(row.id) has an invalid date \(row.date)")
            }

            // The app's own opening-balance carrier goes back where it came from.
            if row.notes == openingBalanceMarker, row.categoryId == nil, row.transferAccountId == nil,
               row.type == "income" || row.type == "expense" {
                let signed = row.type == "income" ? row.amount.value : -row.amount.value
                openingBalance[row.accountId, default: 0] += signed
                openingCount += 1
                continue
            }

            var categoryID = row.categoryId
            if categoryID == nil, let lines = splitCategories[row.id], !lines.isEmpty {
                // The server only allows splits within one parent category,
                // so their common top-level category keeps the Overview's
                // per-category totals exact; only the sub-breakdown is lost.
                let tops = Set(lines.map { categoryByID[$0]?.parentId ?? $0 })
                if tops.count == 1, let top = tops.first {
                    categoryID = top
                    mergedSplits += 1
                } else {
                    uncategorizedSplits += 1
                }
            }
            if !(row.tagIds ?? []).isEmpty {
                withTags += 1
            }

            let currency = (row.currency ?? row.originalCurrency ?? accountCurrency).uppercased()
            let transactionAmount = row.transactionAmount?.value ?? row.originalAmount?.value ?? row.amount.value
            entries.append(
                EntryValue(
                    id: row.id,
                    accountID: row.accountId,
                    categoryID: categoryID,
                    transferAccountID: row.type == "transfer" ? row.transferAccountId : nil,
                    type: row.type,
                    amount: row.amount.value,
                    currency: currency,
                    transactionAmount: transactionAmount,
                    transferAmount: row.type == "transfer" ? row.transferAmount?.value : nil,
                    purpose: row.purpose ?? "ordinary",
                    description: row.description,
                    merchant: row.merchant,
                    notes: row.notes,
                    date: row.date
                )
            )
        }

        let accounts = file.accounts.map { row in
            AccountValue(
                id: row.id,
                name: row.name,
                type: AccountKind(rawValue: row.type)?.rawValue ?? AccountKind.other.rawValue,
                currency: row.currency.uppercased(),
                color: row.color,
                isArchived: row.isArchived,
                initialBalance: openingBalance[row.id] ?? 0
            )
        }
        let categories = file.categories.map { row in
            LedgerCategory(
                id: row.id,
                name: row.name,
                kind: row.kind,
                icon: row.icon,
                color: row.color,
                sortOrder: row.sortOrder,
                isDefault: row.isDefault,
                parentId: row.parentId
            )
        }
        let settingsCurrency = file.appSettings?.currency.uppercased() ?? ""
        let reportingCurrency = isCurrencyCode(settingsCurrency) ? settingsCurrency : fallbackCurrency.uppercased()

        return ImportPlan(
            snapshot: LedgerSnapshot(
                accounts: accounts,
                categories: categories,
                entries: entries,
                reportingCurrency: reportingCurrency
            ),
            exportedAt: file.exportedAt,
            sourceAppVersion: file.appVersion,
            openingBalances: openingCount,
            mergedSplits: mergedSplits,
            uncategorizedSplits: uncategorizedSplits,
            operationsWithTags: withTags,
            ignoredRecords: file.ignoredRecordCount
        )
    }

    private static func isCurrencyCode(_ code: String) -> Bool {
        code.count == 3 && code.unicodeScalars.allSatisfy { $0.isASCII && CharacterSet.uppercaseLetters.contains($0) }
    }
}

extension BackupCodec.CodecError: LocalizedError {
    var errorDescription: String? {
        switch self {
        case .unreadable:
            return L10n.text("backup.error.unreadable")
        case .unsupportedVersion(let version):
            return L10n.format("backup.error.version", String(version))
        case .invalid(let detail):
            return L10n.format("backup.error.invalid", detail)
        }
    }
}
