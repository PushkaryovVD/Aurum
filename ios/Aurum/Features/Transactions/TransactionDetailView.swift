import SwiftUI

/// Details of one operation, from the row already loaded, with edit and
/// delete for those who may write.
struct TransactionDetailView: View {
    @Environment(\.dismiss) private var dismiss
    /// Starts as the tapped row; replaced by what the repository returns
    /// after an edit, so the screen never shows the pre-edit values.
    @State private var transaction: LedgerTransaction
    @State private var isEditing = false
    @State private var confirmDelete = false
    @State private var isDeleting = false
    @State private var deleteError: String?

    private let repository: any FinanceRepository
    private let canEdit: Bool
    private let accountNames: [Int: String]

    init(
        transaction: LedgerTransaction,
        repository: any FinanceRepository,
        canEdit: Bool,
        accountNames: [Int: String]
    ) {
        _transaction = State(initialValue: transaction)
        self.repository = repository
        self.canEdit = canEdit
        self.accountNames = accountNames
    }

    var body: some View {
        list
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    if canEdit {
                        Button("action.edit") { isEditing = true }
                            .disabled(isDeleting)
                    }
                }
            }
            .sheet(isPresented: $isEditing) {
                AddTransactionView(repository: repository, editing: transaction) { saved in
                    transaction = saved
                }
            }
            .confirmationDialog(Text("detail.delete.confirm"), isPresented: $confirmDelete, titleVisibility: .visible) {
                Button("detail.delete", role: .destructive) { delete() }
                Button("action.cancel", role: .cancel) {}
            }
    }

    private var list: some View {
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
                    DetailRow(title: "detail.category", value: CategoryNames.display(category.name))
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

            if transaction.kind == .transfer {
                Section {
                    if let destination = transaction.transferAccountId {
                        DetailRow(title: "detail.toAccount", value: accountNames[destination] ?? "—")
                    }
                    if let transfer = transaction.transferAmount {
                        DetailRow(title: "detail.transferAmount", value: Money.plain(transfer.value))
                    }
                }
            }

            if !transaction.splits.isEmpty {
                Section {
                    ForEach(transaction.splits) { split in
                        HStack {
                            Text(split.category.map { CategoryNames.display($0.name) } ?? L10n.text("detail.deletedCategory"))
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

            if canEdit {
                Section {
                    Button(role: .destructive) {
                        confirmDelete = true
                    } label: {
                        HStack {
                            Text("detail.delete")
                            if isDeleting {
                                Spacer()
                                ProgressView()
                            }
                        }
                    }
                    .disabled(isDeleting)
                    if let deleteError {
                        Text(deleteError)
                            .font(.footnote)
                            .foregroundStyle(Theme.negative)
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(Text("detail.title"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private func delete() {
        deleteError = nil
        isDeleting = true
        Task {
            do {
                try await repository.deleteTransaction(id: transaction.id)
                isDeleting = false
                // The list reloads through the ledger events.
                dismiss()
            } catch {
                isDeleting = false
                if !error.isCancellation {
                    deleteError = error.displayMessage
                }
            }
        }
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
