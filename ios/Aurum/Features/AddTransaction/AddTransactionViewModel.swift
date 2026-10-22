import Foundation
import Observation

/// Form state and validation for a new income/expense operation, producing
/// the backend's TransactionInput (see frontend/src/types TransactionInput
/// and backend/app/schemas/transaction.py TransactionCreate).
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

    private let client: APIClient

    init(client: APIClient) {
        self.client = client
    }

    // MARK: - Loading

    func loadIfNeeded() async {
        guard !reference.hasValue, !reference.isLoading else { return }
        await load()
    }

    func load() async {
        reference.beginLoading()
        do {
            let accounts = try await client.accounts()
            let categories = try await client.categories()
            let data = ReferenceData(accounts: accounts, categories: categories)
            reference.succeed(data)
            if accountID == nil || !accounts.contains(where: { $0.id == accountID }) {
                accountID = accounts.first?.id
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

    var accountCurrency: String { selectedAccount?.currency.uppercased() ?? "" }

    /// Categories of the selected kind, parents followed by their children.
    var categoryOptions: [CategoryOption] {
        guard let all = reference.value?.categories else { return [] }
        let ofKind = all.filter { $0.kind == kind.rawValue }
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
            result.append(CategoryOption(id: root.id, title: root.name, isChild: false))
            let children = ofKind.filter { $0.parentId == root.id }.sorted(by: byOrder)
            for child in children {
                result.append(CategoryOption(id: child.id, title: root.name + " · " + child.name, isChild: true))
            }
        }
        return result
    }

    private var effectiveForeignCurrency: String? {
        guard isForeignCurrency else { return nil }
        let code = currencyCode.trimmingCharacters(in: .whitespaces).uppercased()
        return code == accountCurrency ? nil : code
    }

    // MARK: - Validation

    var amountError: String? {
        guard showValidation else { return nil }
        return DecimalParsing.parseUserAmount(amountText) == nil ? L10n.text("add.error.amount") : nil
    }

    var currencyError: String? {
        guard showValidation, isForeignCurrency else { return nil }
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

    var descriptionError: String? {
        guard showValidation else { return nil }
        return resolvedDescription == nil ? L10n.text("add.error.description") : nil
    }

    /// Description is required by the backend; an empty one falls back to
    /// the chosen category's name, which is what most people would type.
    private var resolvedDescription: String? {
        let typed = descriptionText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !typed.isEmpty { return String(typed.prefix(255)) }
        if let categoryID, let category = reference.value?.categories.first(where: { $0.id == categoryID }) {
            return category.name
        }
        return nil
    }

    // MARK: - Save

    /// Returns true when the operation was created.
    func save() async -> Bool {
        showValidation = true
        saveError = nil
        guard let input = makeInput() else { return false }
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await client.createTransaction(input)
            return true
        } catch {
            if !error.isCancellation {
                saveError = error.displayMessage
            }
            return false
        }
    }

    private func makeInput() -> TransactionInput? {
        guard amountError == nil, accountError == nil, currencyError == nil,
              foreignAmountError == nil, descriptionError == nil,
              let account = selectedAccount,
              let debit = DecimalParsing.parseUserAmount(amountText),
              let description = resolvedDescription
        else { return nil }

        var currency: String?
        var transactionAmount: APIDecimal?
        if let foreign = effectiveForeignCurrency {
            guard let paid = DecimalParsing.parseUserAmount(foreignAmountText) else { return nil }
            currency = foreign
            transactionAmount = APIDecimal(paid)
        }

        // Never send a category that does not belong to the chosen kind.
        let category = categoryOptions.contains(where: { $0.id == categoryID }) ? categoryID : nil

        return TransactionInput(
            accountId: account.id,
            categoryId: category,
            transferAccountId: nil,
            type: kind.rawValue,
            amount: APIDecimal(debit),
            currency: currency,
            transactionAmount: transactionAmount,
            description: description,
            notes: nil,
            date: APIDate.string(from: date),
            tagIds: []
        )
    }

    /// A category of the other kind would be rejected by the backend.
    func kindDidChange() {
        dropCategoryIfMismatched()
    }

    private func dropCategoryIfMismatched() {
        guard let categoryID else { return }
        if !categoryOptions.contains(where: { $0.id == categoryID }) {
            self.categoryID = nil
        }
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
