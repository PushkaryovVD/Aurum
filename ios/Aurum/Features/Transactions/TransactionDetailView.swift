import SwiftUI

/// Read-only details of one operation, from the row already loaded.
struct TransactionDetailView: View {
    let transaction: LedgerTransaction

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                    Text(TransactionPresentation.signedAmount(transaction))
                        .font(.largeTitle.weight(.bold).monospacedDigit())
                        .foregroundStyle(TransactionPresentation.amountColor(transaction))
                        .lineLimit(1)
                        .minimumScaleFactor(0.5)
                    Text(transaction.description)
                        .font(.title3)
                }
                .padding(.vertical, Theme.Spacing.s)
                .accessibilityElement(children: .combine)
            }

            Section {
                DetailRow(title: "detail.type", value: TransactionPresentation.typeTitle(transaction))
                DetailRow(title: "detail.date", value: APIDate.display(transaction.date))
                DetailRow(title: "detail.account", value: transaction.account.name)
                if let category = transaction.category {
                    DetailRow(title: "detail.category", value: category.name)
                }
                if let merchant = transaction.merchant, !merchant.isEmpty {
                    DetailRow(title: "detail.merchant", value: merchant)
                }
            }

            if transaction.isForeignCurrency {
                Section {
                    DetailRow(
                        title: "detail.paid",
                        value: Money.format(transaction.transactionAmount, currency: transaction.currency)
                    )
                    DetailRow(
                        title: "detail.debited",
                        value: Money.format(transaction.amount, currency: transaction.account.currency)
                    )
                } header: {
                    Text("detail.currency")
                }
            }

            if let transfer = transaction.transferAmount, transaction.kind == .transfer {
                Section {
                    DetailRow(title: "detail.transferAmount", value: Money.plain(transfer.value))
                }
            }

            if !transaction.splits.isEmpty {
                Section {
                    ForEach(transaction.splits) { split in
                        HStack {
                            Text(split.category?.name ?? L10n.text("detail.deletedCategory"))
                            Spacer()
                            Text(Money.format(split.amount, currency: transaction.account.currency))
                                .monospacedDigit()
                        }
                        .accessibilityElement(children: .combine)
                    }
                } header: {
                    Text("detail.splits")
                }
            }

            if !transaction.tags.isEmpty {
                Section {
                    Text(transaction.tags.map(\.name).joined(separator: ", "))
                } header: {
                    Text("detail.tags")
                }
            }

            if let notes = transaction.notes, !notes.isEmpty {
                Section {
                    Text(notes)
                } header: {
                    Text("detail.notes")
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(Text("detail.title"))
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct DetailRow: View {
    let title: LocalizedStringKey
    let value: String

    var body: some View {
        LabeledContent {
            Text(value)
                .multilineTextAlignment(.trailing)
        } label: {
            Text(title)
        }
    }
}
