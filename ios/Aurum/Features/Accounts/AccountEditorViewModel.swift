import Foundation
import Observation

/// Form state for adding or editing an account, in either storage mode.
@MainActor
@Observable
final class AccountEditorViewModel {
    var name: String
    var kind: AccountKind
    var currency: String
    var isArchived: Bool
    /// Device mode only; may be zero or negative (e.g. a credit card).
    var initialBalanceText: String

    private(set) var isSaving = false
    private(set) var saveError: String?
    private(set) var showValidation = false

    let isNew: Bool
    /// The server and the device both refuse to relabel the currency of an
    /// account that already has operations.
    let isCurrencyLocked: Bool
    var supportsInitialBalance: Bool { repository.supportsInitialBalance }

    private let repository: any AccountRepository
    private let accountID: Int?
    private let color: String?

    init(repository: any AccountRepository, account: AccountWithBalance?, defaultCurrency: String) {
        self.repository = repository
        self.accountID = account?.id
        self.isNew = account == nil
        self.name = account?.name ?? ""
        self.kind = account.flatMap { AccountKind(rawValue: $0.type) } ?? .checking
        self.currency = account?.currency.uppercased() ?? defaultCurrency.uppercased()
        self.isArchived = account?.isArchived ?? false
        self.color = account?.color
        self.isCurrencyLocked = (account?.transactionCount ?? 0) > 0
        let opening = account?.initialBalance?.value ?? 0
        self.initialBalanceText = opening == 0 ? "" : Self.editableText(opening)
    }

    // MARK: - Validation

    var nameError: String? {
        guard showValidation else { return nil }
        return name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? L10n.text("account.error.name") : nil
    }

    var currencyError: String? {
        guard showValidation else { return nil }
        return LocalRepository.isCurrencyCode(normalizedCurrency) ? nil : L10n.text("add.error.currency")
    }

    var initialBalanceError: String? {
        guard showValidation, supportsInitialBalance else { return nil }
        return DecimalParsing.parseUserSignedAmount(initialBalanceText) == nil ? L10n.text("account.error.balance") : nil
    }

    private var normalizedCurrency: String {
        currency.trimmingCharacters(in: .whitespaces).uppercased()
    }

    // MARK: - Save

    /// Returns true when the account was stored.
    func save() async -> Bool {
        showValidation = true
        saveError = nil
        guard nameError == nil, currencyError == nil, initialBalanceError == nil else { return false }
        let input = AccountInput(
            name: name.trimmingCharacters(in: .whitespacesAndNewlines),
            type: kind.rawValue,
            currency: normalizedCurrency,
            color: color,
            isArchived: isArchived,
            initialBalance: supportsInitialBalance ? (DecimalParsing.parseUserSignedAmount(initialBalanceText) ?? 0) : 0
        )
        isSaving = true
        defer { isSaving = false }
        do {
            if let accountID {
                _ = try await repository.updateAccount(id: accountID, input)
            } else {
                _ = try await repository.createAccount(input)
            }
            return true
        } catch {
            if !error.isCancellation {
                saveError = error.displayMessage
            }
            return false
        }
    }

    /// A stored balance as the user would type it back ("-1250.5").
    private static func editableText(_ value: Decimal) -> String {
        DecimalParsing.wireString(value)
    }
}
