import Foundation
import Observation

/// Form state and validation for an operation — a new one or an edit of an
/// existing one; income, expense or a transfer between own accounts. It
/// produces a storage-independent TransactionDraft; the repository turns it
/// into the backend's TransactionInput / PATCH body (see frontend/src/types
/// TransactionInput and backend/app/schemas/transaction.py) or a device row.
@MainActor
@Observable
final class AddTransactionViewModel {
    // MARK: Reference data
    private(set) var reference = RemoteContent<ReferenceData>()

    // MARK: Form fields
    /// Changing it should be followed by `kindDidChange()` (the view does
    /// this via onChange) — no didSet, to stay clear of @Observable's
    /// property rewriting.
    var kind: TransactionKind = .expense
    var amountText = ""
    var accountID: Int?
    /// Transfers: where the money goes.
    var transferAccountID: Int?
    /// Cross-currency transfers: what the destination was credited, in its
    /// own currency.
    var transferAmountText = ""
    /// Paid in a currency other than the account's (e.g. USD with a KZT card).
    var isForeignCurrency = false
    var currencyCode = ""
    /// The amount in the operation's own currency (foreign mode only).
    var foreignAmountText = ""
    var categoryID: Int?
    var date = Date()
    var descriptionText = ""

    // MARK: Submission
    private(set) var isSaving = false
    private(set) var saveError: String?
    /// Shown only after the first save attempt, so an untouched form is not
    /// covered in red.
    private(set) var showValidation = false

    /// The operation being edited; nil for a new one.
    let editing: LedgerTransaction?

    private let repository: any FinanceRepository

    init(repository: any FinanceRepository, editing: LedgerTransaction? = nil) {
        self.repository = repository
        self.editing = editing
        if let editing {
            prefill(from: editing)
        }
    }

    var isNew: Bool { editing == nil }

    /// Split operations are edited on the web: this form has no split lines,
    /// and saving it would have to drop them.
    var isLockedSplit: Bool { !(editing?.splits.isEmpty ?? true) }

    // MARK: - Loading

    func loadIfNeeded() async {
        guard !reference.hasValue, !reference.isLoading else { return }
        await load()
    }

    func load() async {
        reference.beginLoading()
        do {
            // Archived accounts are loaded too, but only offered when the
            // edited operation already uses one.
            let all = try await repository.accounts(includeArchived: true)
            let categories = try await repository.categories()
            let keep = Set([editing?.accountId, editing?.transferAccountId].compactMap { $0 })
            let accounts = all.filter { !$0.isArchived || keep.contains($0.id) }
            reference.succeed(ReferenceData(accounts: accounts, categories: categories))
            if accountID == nil || !accounts.contains(where: { $0.id == accountID }) {
                accountID = accounts.first?.id
            }
            if let transferAccountID, !accounts.contains(where: { $0.id == transferAccountID }) {
                self.transferAccountID = nil
            }
            dropCategoryIfMismatched()
        } catch {
            if error.isCancellation {
                reference.cancel()
            } else {
                reference.fail(error.displayMessage)
            }
        }
    }

    // MARK: - Derived

    var accounts: [AccountWithBalance] { reference.value?.accounts ?? [] }

    var selectedAccount: AccountWithBalance? {
        accounts.first { $0.id == accountID }
    }

    var destinationAccount: AccountWithBalance? {
        accounts.first { $0.id == transferAccountID }
    }

    /// Accounts a transfer can go to: every other one.
    var destinationOptions: [AccountWithBalance] {
        accounts.filter { $0.id != accountID }
    }

    var accountCurrency: String { selectedAccount?.currency.uppercased() ?? "" }

    var destinationCurrency: String { destinationAccount?.currency.uppercased() ?? "" }

    /// A transfer between accounts in different currencies needs the
    /// credited amount too (the server requires transfer_amount then).
    var isCrossCurrencyTransfer: Bool {
        kind == .transfer && destinationAccount != nil && destinationCurrency != accountCurrency
    }

    /// Categories of the selected kind, parents followed by their children.
    var categoryOptions: [CategoryOption] {
        guard kind != .transfer, let all = reference.value?.categories else { return [] }
        var ofKind = all.filter { $0.kind == kind.rawValue }
        // An income filed under an expense category is a refund on the
        // server; keep that category selectable when editing such a row.
        if kind == .income, let original = editing?.categoryId,
           let category = all.first(where: { $0.id == original }), category.kind != kind.rawValue {
            ofKind.append(category)
        }
        let byOrder: (LedgerCategory, LedgerCategory) -> Bool = { lhs, rhs in
            if lhs.sortOrder != rhs.sortOrder { return lhs.sortOrder < rhs.sortOrder }
            return lhs.name.localizedStandardCompare(rhs.name) == .orderedAscending
        }
        let ids = Set(ofKind.map(\.id))
        // A child whose parent is missing (other kind / deleted) is listed
        // at the top level rather than dropped.
        let roots = ofKind.filter { $0.parentId == nil || !ids.contains($0.parentId ?? -1) }.sorted(by: byOrder)
        var result: [CategoryOption] = []
        for root in roots {
            let rootName = CategoryNames.display(root.name)
            result.append(CategoryOption(id: root.id, title: rootName, isChild: false))
            let children = ofKind.filter { $0.parentId == root.id }.sorted(by: byOrder)
            for child in children {
                result.append(CategoryOption(id: child.id, title: rootName + " · " + CategoryNames.display(child.name), isChild: true))
            }
        }
        return result
    }

    private var effectiveForeignCurrency: String? {
        guard isForeignCurrency, kind != .transfer else { return nil }
        let code = currencyCode.trimmingCharacters(in: .whitespaces).uppercased()
        return code == accountCurrency ? nil : code
    }

    // MARK: - Validation

    var amountError: String? {
        guard showValidation else { return nil }
        return DecimalParsing.parseUserAmount(amountText) == nil ? L10n.text("add.error.amount") : nil
    }

    var currencyError: String? {
        guard showValidation, isForeignCurrency, kind != .transfer else { return nil }
        let code = currencyCode.trimmingCharacters(in: .whitespaces)
        let valid = code.count == 3 && code.unicodeScalars.allSatisfy { CharacterSet.letters.contains($0) && $0.isASCII }
        return valid ? nil : L10n.text("add.error.currency")
    }

    var foreignAmountError: String? {
        guard showValidation, effectiveForeignCurrency != nil else { return nil }
        return DecimalParsing.parseUserAmount(foreignAmountText) == nil ? L10n.text("add.error.amount") : nil
    }

    var accountError: String? {
        guard showValidation else { return nil }
        return selectedAccount == nil ? L10n.text("add.error.account") : nil
    }

    var destinationError: String? {
        guard showValidation, kind == .transfer else { return nil }
        guard let destination = destinationAccount else { return L10n.text("add.error.destination") }
        return destination.id == accountID ? L10n.text("add.error.sameAccount") : nil
    }

    var transferAmountError: String? {
        guard showValidation, isCrossCurrencyTransfer else { return nil }
        return DecimalParsing.parseUserAmount(transferAmountText) == nil ? L10n.text("add.error.transferAmount") : nil
    }

    var descriptionError: String? {
        guard showValidation else { return nil }
        return resolvedDescription == nil ? L10n.text("add.error.description") : nil
    }

    /// Description is required by the backend; an empty one falls back to
    /// the chosen category's name (or "Transfer"), which is what most
    /// people would type.
    private var resolvedDescription: String? {
        let typed = descriptionText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !typed.isEmpty { return String(typed.prefix(255)) }
        if kind == .transfer {
            return L10n.text("type.transfer")
        }
        if let categoryID, let category = reference.value?.categories.first(where: { $0.id == categoryID }) {
            return CategoryNames.display(category.name)
        }
        return nil
    }

    // MARK: - Save

    /// Returns the stored operation, or nil when it was not saved.
    func save() async -> LedgerTransaction? {
        showValidation = true
        saveError = nil
        guard !isLockedSplit, let draft = makeDraft() else { return nil }
        isSaving = true
        defer { isSaving = false }
        do {
            if let editing {
                return try await repository.updateTransaction(id: editing.id, draft)
            }
            return try await repository.createTransaction(draft)
        } catch {
            if !error.isCancellation {
                saveError = error.displayMessage
            }
            return nil
        }
    }

    private func makeDraft() -> TransactionDraft? {
        guard amountError == nil, accountError == nil, currencyError == nil,
              foreignAmountError == nil, destinationError == nil,
              transferAmountError == nil, descriptionError == nil,
              let account = selectedAccount,
              let debit = DecimalParsing.parseUserAmount(amountText),
              let description = resolvedDescription
        else { return nil }

        var foreignCurrency: String?
        var foreignAmount: Decimal?
        if let foreign = effectiveForeignCurrency {
            guard let paid = DecimalParsing.parseUserAmount(foreignAmountText) else { return nil }
            foreignCurrency = foreign
            foreignAmount = paid
        }

        var transferAccount: Int?
        var credited: Decimal?
        if kind == .transfer {
            guard let destination = destinationAccount else { return nil }
            transferAccount = destination.id
            if isCrossCurrencyTransfer {
                guard let amount = DecimalParsing.parseUserAmount(transferAmountText) else { return nil }
                credited = amount
            }
        }

        // Never send a category that does not belong to the chosen kind.
        let category = categoryOptions.contains(where: { $0.id == categoryID }) ? categoryID : nil

        return TransactionDraft(
            kind: kind,
            accountID: account.id,
            accountCurrency: account.currency.uppercased(),
            categoryID: kind == .transfer ? nil : category,
            transferAccountID: transferAccount,
            amount: debit,
            foreignCurrency: foreignCurrency,
            foreignAmount: foreignAmount,
            transferAmount: credited,
            description: description,
            date: APIDate.string(from: date)
        )
    }

    /// A category of the other kind would be rejected by the backend, and a
    /// transfer carries none at all.
    func kindDidChange() {
        if kind == .transfer {
            isForeignCurrency = false
            categoryID = nil
        }
        dropCategoryIfMismatched()
    }

    /// The source changed: a transfer cannot go to the same account, and a
    /// credited amount typed for another pair of currencies no longer fits.
    func accountDidChange() {
        if transferAccountID == accountID {
            transferAccountID = nil
        }
        transferAmountText = ""
    }

    private func dropCategoryIfMismatched() {
        guard let categoryID else { return }
        if !categoryOptions.contains(where: { $0.id == categoryID }) {
            self.categoryID = nil
        }
    }

    private func prefill(from transaction: LedgerTransaction) {
        kind = transaction.kind ?? .expense
        accountID = transaction.accountId
        amountText = DecimalParsing.wireString(transaction.amount.value)
        if transaction.isForeignCurrency, kind != .transfer {
            isForeignCurrency = true
            currencyCode = transaction.currency.uppercased()
            foreignAmountText = DecimalParsing.wireString(transaction.transactionAmount.value)
        }
        transferAccountID = transaction.transferAccountId
        if let credited = transaction.transferAmount?.value, credited != transaction.amount.value {
            transferAmountText = DecimalParsing.wireString(credited)
        }
        categoryID = transaction.categoryId
        date = APIDate.parse(transaction.date) ?? Date()
        descriptionText = transaction.description
    }
}

struct ReferenceData: Sendable {
    let accounts: [AccountWithBalance]
    let categories: [LedgerCategory]
}

struct CategoryOption: Identifiable, Hashable, Sendable {
    let id: Int
    let title: String
    let isChild: Bool
}
