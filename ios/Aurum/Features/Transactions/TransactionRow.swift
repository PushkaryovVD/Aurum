import SwiftUI

/// One operation in the list: category, description, account and the signed
/// amount in the account's currency (what moved the balance).
struct TransactionRow: View {
    let transaction: LedgerTransaction

    var body: some View {
        HStack(alignment: .center, spacing: Theme.Spacing.m) {
            TransactionIcon(transaction: transaction)

            VStack(alignment: .leading, spacing: 2) {
                Text(transaction.description)
                    .font(.body)
                    .lineLimit(2)
                Text(subtitle)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: Theme.Spacing.s)

            VStack(alignment: .trailing, spacing: 2) {
                Text(TransactionPresentation.signedAmount(transaction))
                    .font(.body.weight(.semibold).monospacedDigit())
                    .foregroundStyle(TransactionPresentation.amountColor(transaction))
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                if transaction.isForeignCurrency {
                    Text(Money.format(transaction.transactionAmount, currency: transaction.currency))
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }

    private var subtitle: String {
        var parts: [String] = []
        if let category = transaction.category?.name {
            parts.append(CategoryNames.display(category))
        } else if transaction.kind == .transfer {
            parts.append(L10n.text("type.transfer"))
        } else if !transaction.splits.isEmpty {
            parts.append(L10n.text("transaction.split"))
        }
        parts.append(transaction.account.name)
        return parts.joined(separator: " · ")
    }
}

struct TransactionIcon: View {
    let transaction: LedgerTransaction

    private var symbol: String {
        switch transaction.kind {
        case .income: return "arrow.down.left"
        case .transfer: return "arrow.left.arrow.right"
        case .expense, .none: return "arrow.up.right"
        }
    }

    private var tint: Color {
        Color(hex: transaction.category?.color) ?? .secondary
    }

    var body: some View {
        Image(systemName: symbol)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(tint)
            .frame(width: 36, height: 36)
            .background(tint.opacity(0.15), in: Circle())
            .accessibilityHidden(true)
    }
}

/// Shared wording/colour rules for an operation's amount.
enum TransactionPresentation {
    static func signedAmount(_ transaction: LedgerTransaction) -> String {
        let currency = transaction.account.currency
        switch transaction.kind {
        case .income:
            return Money.signed(transaction.amount.value, currency: currency, negative: false)
        case .expense:
            return Money.signed(transaction.amount.value, currency: currency, negative: true)
        case .transfer, .none:
            return Money.format(transaction.amount, currency: currency)
        }
    }

    static func amountColor(_ transaction: LedgerTransaction) -> Color {
        transaction.kind == .income ? Theme.income : Theme.expense
    }

    static func typeTitle(_ transaction: LedgerTransaction) -> String {
        switch transaction.kind {
        case .income: return L10n.text("type.income")
        case .expense: return L10n.text("type.expense")
        case .transfer: return L10n.text("type.transfer")
        case .none: return transaction.type
        }
    }
}
