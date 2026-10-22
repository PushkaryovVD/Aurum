import Foundation

// The on-device ledger's arithmetic, as pure functions over plain values —
// no SwiftData, no I/O, no clock (the caller passes "today" where needed), so
// every rule here can be checked with a handful of literals.
//
// Each function mirrors a server routine and says which one; when the server
// changes its semantics, this is the one file to update:
//   balances          — backend/app/services/account_service.py account_balances
//   dashboardSummary  — backend/app/services/dashboard_service.py
//   spendingRollup    — backend/app/services/category_rollup.py
//   page              — GET /api/transactions (backend/app/api/routes/transactions.py)

/// One account as the arithmetic needs it.
struct AccountValue: Sendable, Hashable {
    let id: Int
    let name: String
    let type: String
    let currency: String
    let color: String?
    let isArchived: Bool
    /// Device-only opening balance, in the account's currency.
    let initialBalance: Decimal
}

/// One stored operation as the arithmetic needs it.
struct EntryValue: Sendable, Hashable {
    let id: Int
    let accountID: Int
    let categoryID: Int?
    let transferAccountID: Int?
    /// "income" | "expense" | "transfer"
    let type: String
    /// Always positive, in the account's currency — the number that moves
    /// the balance.
    let amount: Decimal
    /// The operation's own currency and the amount in it.
    let currency: String
    let transactionAmount: Decimal
    /// Transfers: credited to the destination, in its currency.
    let transferAmount: Decimal?
    /// backend TransactionPurpose raw value; "ordinary" for everything the
    /// app creates itself, other values arrive only from a server backup.
    let purpose: String
    let description: String
    /// Carried for display and backups only; no rule here reads it.
    let merchant: String?
    let notes: String?
    /// "YYYY-MM-DD"
    let date: String
}

enum LedgerMath {
    /// Same as the server's dashboard cap: the 9th+ category folds into
    /// "Other" with a reserved muted color.
    static let maxChartSlices = 8
    static let otherSliceColor = "#898781"
    static let unknownCategoryColor = "#898781"

    // MARK: - Balances

    /// Every account's balance and operation count. Income adds, expense
    /// subtracts, a transfer moves `amount` out of the source and
    /// `transferAmount ?? amount` into the destination; the device-only
    /// opening balance is the starting point. A transfer counts towards its
    /// source account only, like on the server.
    static func balances(
        accounts: [AccountValue],
        entries: [EntryValue]
    ) -> (balances: [Int: Decimal], counts: [Int: Int]) {
        var balances: [Int: Decimal] = [:]
        var counts: [Int: Int] = [:]
        for account in accounts {
            balances[account.id] = account.initialBalance
        }
        for entry in entries {
            counts[entry.accountID, default: 0] += 1
            switch entry.type {
            case TransactionKind.income.rawValue:
                balances[entry.accountID, default: 0] += entry.amount
            case TransactionKind.expense.rawValue:
                balances[entry.accountID, default: 0] -= entry.amount
            case TransactionKind.transfer.rawValue:
                balances[entry.accountID, default: 0] -= entry.amount
                if let destination = entry.transferAccountID {
                    balances[destination, default: 0] += entry.transferAmount ?? entry.amount
                }
            default:
                // An unknown type cannot be interpreted; it moves nothing
                // rather than guessing a direction.
                break
            }
        }
        return (balances, counts)
    }

    /// GET /api/accounts equivalent: ordered by name, archived ones only on
    /// request.
    static func accountsWithBalance(
        accounts: [AccountValue],
        entries: [EntryValue],
        includeArchived: Bool
    ) -> [AccountWithBalance] {
        let computed = Self.balances(accounts: accounts, entries: entries)
        return accounts
            .filter { includeArchived || !$0.isArchived }
            .sorted { lhs, rhs in
                let order = lhs.name.localizedStandardCompare(rhs.name)
                return order == .orderedSame ? lhs.id < rhs.id : order == .orderedAscending
            }
            .map { account in
                AccountWithBalance(
                    id: account.id,
                    name: account.name,
                    type: account.type,
                    currency: account.currency,
                    color: account.color,
                    isArchived: account.isArchived,
                    balance: APIDecimal(computed.balances[account.id] ?? 0),
                    transactionCount: computed.counts[account.id] ?? 0,
                    initialBalance: APIDecimal(account.initialBalance)
                )
            }
    }

    // MARK: - Dashboard

    /// The month's Overview, computed the way dashboard_service does it,
    /// with the device's reporting currency in the role the server gives to
    /// KZT:
    /// - "real income" / "spent" / "transferred out" are the month's income /
    ///   expense / transfer totals, so a transfer between own accounts is
    ///   never income or spending; investment trades are left out of them;
    /// - an operation counts only if its amount is known in the reporting
    ///   currency. The device has no exchange rates, so that means "the
    ///   account is in the reporting currency"; others are left out and
    ///   reported in `excludedCurrencies` (the server likewise drops a row
    ///   without a KZT snapshot);
    /// - net = real income − spent;
    /// - the balance is all-time across every account (archived included),
    ///   per currency; a currency other than the reporting one has no rate
    ///   and is shown but not added to the total, which is then `incomplete`.
    static func dashboardSummary(
        month: MonthRef,
        accounts: [AccountValue],
        categories: [LedgerCategory],
        entries: [EntryValue],
        reportingCurrency: String,
        otherName: String
    ) -> DashboardSummary {
        let reporting = reportingCurrency.uppercased()
        let currencyByAccount = Dictionary(accounts.map { ($0.id, $0.currency.uppercased()) }, uniquingKeysWith: { first, _ in first })
        let prefix = monthPrefix(month)
        let inMonth = entries.filter { $0.date.hasPrefix(prefix) }

        var income: Decimal = 0
        var spent: Decimal = 0
        var transferred: Decimal = 0
        var excluded = Set<String>()
        for entry in inMonth where entry.purpose != "investment_trade" {
            guard let amount = reportingAmount(entry, currencyByAccount: currencyByAccount, reporting: reporting) else {
                if let currency = currencyByAccount[entry.accountID] {
                    excluded.insert(currency)
                }
                continue
            }
            switch entry.type {
            case TransactionKind.income.rawValue: income += amount
            case TransactionKind.expense.rawValue: spent += amount
            case TransactionKind.transfer.rawValue: transferred += amount
            default: break
            }
        }

        let rollup = spendingRollup(
            entries: inMonth,
            categories: categories,
            currencyByAccount: currencyByAccount,
            reporting: reporting
        )
        let top = rollup.prefix(maxChartSlices)
        let rest = rollup.dropFirst(maxChartSlices)
        var items: [CategoryBreakdownItem] = top.map { row in
            CategoryBreakdownItem(
                categoryId: row.categoryID,
                name: row.name,
                color: row.color,
                icon: row.icon,
                amount: APIDecimal(row.amount),
                percent: percent(row.amount, of: spent),
                children: row.children.map { child in
                    CategoryBreakdownChildItem(
                        categoryId: child.categoryID,
                        name: child.name,
                        color: child.color,
                        icon: child.icon,
                        amount: APIDecimal(child.amount)
                    )
                }
            )
        }
        if !rest.isEmpty {
            let otherAmount = rest.reduce(Decimal(0)) { $0 + $1.amount }
            items.append(
                CategoryBreakdownItem(
                    categoryId: nil,
                    name: otherName,
                    color: otherSliceColor,
                    icon: "more-horizontal",
                    amount: APIDecimal(otherAmount),
                    percent: percent(otherAmount, of: spent),
                    children: []
                )
            )
        }

        return DashboardSummary(
            year: month.year,
            month: month.month,
            realIncome: APIDecimal(income),
            spent: APIDecimal(spent),
            net: APIDecimal(income - spent),
            transferredOut: APIDecimal(transferred),
            spendingByCategory: items,
            balance: balanceSummary(accounts: accounts, entries: entries, reportingCurrency: reporting),
            excludedCurrencies: excluded.sorted()
        )
    }

    /// get_balance_summary without exchange rates.
    static func balanceSummary(
        accounts: [AccountValue],
        entries: [EntryValue],
        reportingCurrency: String
    ) -> BalanceSummary {
        let reporting = reportingCurrency.uppercased()
        let computed = Self.balances(accounts: accounts, entries: entries)
        var byCurrency: [String: Decimal] = [:]
        for account in accounts {
            byCurrency[account.currency.uppercased(), default: 0] += computed.balances[account.id] ?? 0
        }
        var total: Decimal = 0
        var incomplete = false
        var items: [CurrencyBalance] = []
        for currency in byCurrency.keys.sorted() {
            let amount = byCurrency[currency] ?? 0
            if amount == 0 {
                // Zero is zero in every currency — no rate needed.
                items.append(CurrencyBalance(currency: currency, amount: APIDecimal(0), amountReporting: APIDecimal(0), rateToKzt: nil, rateDate: nil))
            } else if currency == reporting {
                total += amount
                items.append(CurrencyBalance(currency: currency, amount: APIDecimal(amount), amountReporting: APIDecimal(amount), rateToKzt: nil, rateDate: nil))
            } else {
                incomplete = true
                items.append(CurrencyBalance(currency: currency, amount: APIDecimal(amount), amountReporting: nil, rateToKzt: nil, rateDate: nil))
            }
        }
        return BalanceSummary(reportingCurrency: reporting, total: APIDecimal(total), incomplete: incomplete, items: items)
    }

    // MARK: - Category rollup

    struct RollupChild: Sendable, Hashable {
        let categoryID: Int
        let name: String
        let color: String
        let icon: String?
        let amount: Decimal
    }

    struct RollupRow: Sendable, Hashable {
        let categoryID: Int
        let name: String
        let color: String
        let icon: String?
        let sortOrder: Int
        let amount: Decimal
        /// Only when more than one leaf category fed this total.
        let children: [RollupChild]
    }

    /// Expense per top-level category: a subcategory's amount rolls up into
    /// its parent; uncategorized spending is not a slice (same as the
    /// server). Sorted by amount desc, then sort order.
    static func spendingRollup(
        entries: [EntryValue],
        categories: [LedgerCategory],
        currencyByAccount: [Int: String],
        reporting: String
    ) -> [RollupRow] {
        let byID = Dictionary(categories.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        var amountByTop: [Int: Decimal] = [:]
        var amountByLeaf: [Int: [Int: Decimal]] = [:]
        for entry in entries where entry.type == TransactionKind.expense.rawValue {
            guard let categoryID = entry.categoryID,
                  let amount = reportingAmount(entry, currencyByAccount: currencyByAccount, reporting: reporting)
            else { continue }
            let top = byID[categoryID]?.parentId ?? categoryID
            amountByTop[top, default: 0] += amount
            amountByLeaf[top, default: [:]][categoryID, default: 0] += amount
        }

        var rows: [RollupRow] = []
        for (topID, amount) in amountByTop {
            let category = byID[topID]
            let leaves = amountByLeaf[topID] ?? [:]
            var children: [RollupChild] = []
            if leaves.count > 1 {
                children = leaves
                    .sorted { lhs, rhs in lhs.value == rhs.value ? lhs.key < rhs.key : lhs.value > rhs.value }
                    .map { pair in
                        let leaf = byID[pair.key]
                        return RollupChild(
                            categoryID: pair.key,
                            name: leaf?.name ?? "?",
                            color: leaf?.color ?? unknownCategoryColor,
                            icon: leaf?.icon,
                            amount: pair.value
                        )
                    }
            }
            rows.append(
                RollupRow(
                    categoryID: topID,
                    name: category?.name ?? "?",
                    color: category?.color ?? unknownCategoryColor,
                    icon: category?.icon,
                    sortOrder: category?.sortOrder ?? 0,
                    amount: amount,
                    children: children
                )
            )
        }
        rows.sort { lhs, rhs in
            if lhs.amount != rhs.amount { return lhs.amount > rhs.amount }
            if lhs.sortOrder != rhs.sortOrder { return lhs.sortOrder < rhs.sortOrder }
            return lhs.categoryID < rhs.categoryID
        }
        return rows
    }

    // MARK: - Listing

    /// GET /api/transactions equivalent: optional month, case-insensitive
    /// search over description and notes, newest first (date desc, id desc),
    /// 1-based pages.
    static func page(
        _ entries: [EntryValue],
        filter: TransactionFilter,
        page: Int,
        pageSize: Int
    ) -> (items: [EntryValue], total: Int) {
        var matching = entries
        if let month = filter.month {
            let prefix = monthPrefix(month)
            matching = matching.filter { $0.date.hasPrefix(prefix) }
        }
        let search = filter.search.trimmingCharacters(in: .whitespacesAndNewlines)
        if !search.isEmpty {
            matching = matching.filter { entry in
                entry.description.localizedCaseInsensitiveContains(search)
                    || (entry.notes?.localizedCaseInsensitiveContains(search) ?? false)
            }
        }
        matching.sort { lhs, rhs in
            lhs.date == rhs.date ? lhs.id > rhs.id : lhs.date > rhs.date
        }
        let size = max(pageSize, 1)
        let start = max(page - 1, 0) * size
        guard start < matching.count else { return ([], matching.count) }
        let end = min(start + size, matching.count)
        return (Array(matching[start..<end]), matching.count)
    }

    // MARK: - Helpers

    /// "2026-10-" — the prefix every "YYYY-MM-DD" date of that month has.
    static func monthPrefix(_ month: MonthRef) -> String {
        let year = String(month.year)
        let monthText = month.month < 10 ? "0" + String(month.month) : String(month.month)
        return year + "-" + monthText + "-"
    }

    /// The entry's account-currency amount when that currency is the
    /// reporting one; nil when it would need an exchange rate.
    private static func reportingAmount(
        _ entry: EntryValue,
        currencyByAccount: [Int: String],
        reporting: String
    ) -> Decimal? {
        guard let currency = currencyByAccount[entry.accountID], currency == reporting else { return nil }
        return entry.amount
    }

    private static func percent(_ amount: Decimal, of total: Decimal) -> Double {
        guard total != 0 else { return 0 }
        return NSDecimalNumber(decimal: amount / total * 100).doubleValue
    }
}
