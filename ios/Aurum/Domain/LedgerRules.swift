import Foundation

/// The server's write-time rules for an operation, applied on the device so
/// a row stored on the iPhone is always one the server would also accept
/// (and therefore restores cleanly from a backup). Pure: it only looks at
/// the values it is given.
///
/// Mirrors backend/app/schemas/transaction.py (transfer_rule_violation,
/// field limits, capitalize_first_letter) and routes/transactions.py
/// (_currency_fields, _ensure_category_matches_type).
enum LedgerRules {
    static let maxDescriptionLength = 255

    /// A draft that passed validation, with every derived field resolved.
    struct Resolved: Sendable, Hashable {
        let type: String
        let accountID: Int
        let categoryID: Int?
        let transferAccountID: Int?
        let amount: Decimal
        let currency: String
        let transactionAmount: Decimal
        let transferAmount: Decimal?
        let description: String
        let date: String
    }

    static func resolve(
        _ draft: TransactionDraft,
        accounts: [AccountValue],
        categories: [LedgerCategory]
    ) -> Result<Resolved, LedgerError> {
        guard let account = accounts.first(where: { $0.id == draft.accountID }) else {
            return .failure(.accountNotFound)
        }
        guard draft.amount > 0 else {
            return .failure(.invalid(L10n.text("add.error.amount")))
        }
        guard APIDate.parse(draft.date) != nil else {
            return .failure(.invalid(L10n.text("ledger.error.date")))
        }
        let description = capitalizeFirstLetter(
            String(draft.description.trimmingCharacters(in: .whitespacesAndNewlines).prefix(maxDescriptionLength))
        )
        guard !description.isEmpty else {
            return .failure(.invalid(L10n.text("add.error.description")))
        }

        // Transaction currency: one currency means one number.
        let accountCurrency = account.currency.uppercased()
        let currency = (draft.foreignCurrency?.uppercased()).flatMap { $0.isEmpty ? nil : $0 } ?? accountCurrency
        let transactionAmount: Decimal
        if currency == accountCurrency {
            transactionAmount = draft.amount
        } else {
            guard let foreign = draft.foreignAmount, foreign > 0 else {
                return .failure(.invalid(L10n.text("add.error.amount")))
            }
            transactionAmount = foreign
        }

        switch draft.kind {
        case .transfer:
            guard let destinationID = draft.transferAccountID else {
                return .failure(.invalid(L10n.text("add.error.destination")))
            }
            guard destinationID != account.id else {
                return .failure(.invalid(L10n.text("add.error.sameAccount")))
            }
            guard let destination = accounts.first(where: { $0.id == destinationID }) else {
                return .failure(.accountNotFound)
            }
            let transferAmount: Decimal
            if destination.currency.uppercased() == accountCurrency {
                transferAmount = draft.amount
            } else {
                guard let credited = draft.transferAmount, credited > 0 else {
                    return .failure(.invalid(L10n.text("add.error.transferAmount")))
                }
                transferAmount = credited
            }
            return .success(
                Resolved(
                    type: TransactionKind.transfer.rawValue,
                    accountID: account.id,
                    categoryID: nil,
                    transferAccountID: destination.id,
                    amount: draft.amount,
                    currency: currency,
                    transactionAmount: transactionAmount,
                    transferAmount: transferAmount,
                    description: description,
                    date: draft.date
                )
            )

        case .income, .expense:
            if let categoryID = draft.categoryID {
                guard let category = categories.first(where: { $0.id == categoryID }) else {
                    return .failure(.categoryNotFound)
                }
                // Expense needs an expense category; income takes an income
                // category or an expense one (a refund), as on the server.
                let allowed = category.kind == draft.kind.rawValue
                    || (draft.kind == .income && category.kind == TransactionKind.expense.rawValue)
                guard allowed else {
                    return .failure(.invalid(L10n.text("ledger.error.categoryKind")))
                }
            }
            return .success(
                Resolved(
                    type: draft.kind.rawValue,
                    accountID: account.id,
                    categoryID: draft.categoryID,
                    transferAccountID: nil,
                    amount: draft.amount,
                    currency: currency,
                    transactionAmount: transactionAmount,
                    transferAmount: nil,
                    description: description,
                    date: draft.date
                )
            )
        }
    }

    /// "траты" -> "Траты"; the rest of the text is left exactly as typed.
    static func capitalizeFirstLetter(_ text: String) -> String {
        guard let first = text.first else { return text }
        return first.uppercased() + String(text.dropFirst())
    }
}
