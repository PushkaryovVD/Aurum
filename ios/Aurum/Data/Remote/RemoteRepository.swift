import Foundation

/// "My server" mode: every call goes to the user's Aurum server through the
/// existing APIClient. Business rules (balances, the dashboard, validation)
/// stay on the server; this type only maps the shared write models onto the
/// API's request shapes.
@MainActor
final class RemoteRepository: FinanceRepository {
    let client: APIClient
    let events: LedgerEvents

    init(client: APIClient) {
        self.client = client
        self.events = LedgerEvents()
    }

    // MARK: Accounts

    var supportsInitialBalance: Bool { false }

    func accounts(includeArchived: Bool) async throws -> [AccountWithBalance] {
        try await client.accounts(includeArchived: includeArchived)
    }

    func createAccount(_ input: AccountInput) async throws -> AccountWithBalance {
        let body = AccountCreateBody(
            name: input.name,
            type: input.type,
            currency: input.currency.uppercased(),
            color: input.color
        )
        let account = try await client.createAccount(body)
        events.ledgerDidChange()
        return account
    }

    func updateAccount(id: Int, _ input: AccountInput) async throws -> AccountWithBalance {
        // The current row decides whether the currency key is sent at all.
        let current = try await client.accounts(includeArchived: true).first { $0.id == id }
        let newCurrency = input.currency.uppercased()
        let changesCurrency = current.map { $0.currency.uppercased() != newCurrency } ?? true
        let body = AccountPatchBody(
            name: input.name,
            type: input.type,
            isArchived: input.isArchived,
            currency: changesCurrency ? newCurrency : nil
        )
        let account = try await client.updateAccount(id: id, body)
        events.ledgerDidChange()
        return account
    }

    // MARK: Categories

    func categories() async throws -> [LedgerCategory] {
        try await client.categories()
    }

    // MARK: Transactions

    func transactions(_ filter: TransactionFilter, page: Int, pageSize: Int) async throws -> TransactionPage {
        try await client.transactions(filter, page: page, pageSize: pageSize)
    }

    func createTransaction(_ draft: TransactionDraft) async throws -> LedgerTransaction {
        let isTransfer = draft.kind == .transfer
        let input = TransactionInput(
            accountId: draft.accountID,
            categoryId: isTransfer ? nil : draft.categoryID,
            transferAccountId: isTransfer ? draft.transferAccountID : nil,
            type: draft.kind.rawValue,
            amount: APIDecimal(draft.amount),
            currency: draft.foreignCurrency,
            transactionAmount: draft.foreignAmount.map { APIDecimal($0) },
            // Same as the web form: a same-currency transfer states the
            // credited amount equal to the debit.
            transferAmount: isTransfer ? APIDecimal(draft.transferAmount ?? draft.amount) : nil,
            description: draft.description,
            notes: nil,
            date: draft.date,
            tagIds: []
        )
        let created = try await client.createTransaction(input)
        events.ledgerDidChange()
        return created
    }

    func updateTransaction(id: Int, _ draft: TransactionDraft) async throws -> LedgerTransaction {
        let isTransfer = draft.kind == .transfer
        let currency = (draft.foreignCurrency ?? draft.accountCurrency).uppercased()
        let patch = TransactionPatch(
            accountId: draft.accountID,
            type: draft.kind.rawValue,
            amount: APIDecimal(draft.amount),
            currency: currency,
            transactionAmount: APIDecimal(draft.foreignCurrency == nil ? draft.amount : (draft.foreignAmount ?? draft.amount)),
            categoryId: isTransfer ? nil : draft.categoryID,
            transferAccountId: isTransfer ? draft.transferAccountID : nil,
            transferAmount: isTransfer ? APIDecimal(draft.transferAmount ?? draft.amount) : nil,
            description: draft.description,
            date: draft.date
        )
        let updated = try await client.updateTransaction(id: id, patch)
        events.ledgerDidChange()
        return updated
    }

    func deleteTransaction(id: Int) async throws {
        try await client.deleteTransaction(id: id)
        events.ledgerDidChange()
    }

    // MARK: Dashboard

    func dashboardSummary(month: MonthRef) async throws -> DashboardSummary {
        try await client.dashboardSummary(month: month)
    }
}
