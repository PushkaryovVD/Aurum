import SwiftUI

/// Sheet for recording an income, an expense or a transfer between own
/// accounts — or for editing an existing operation (same form, prefilled).
struct AddTransactionView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var model: AddTransactionViewModel
    @FocusState private var focusedField: Field?

    private let onSaved: (LedgerTransaction) -> Void

    private enum Field: Hashable {
        case amount
        case currency
        case foreignAmount
        case transferAmount
        case description
    }

    init(
        repository: any FinanceRepository,
        editing: LedgerTransaction? = nil,
        onSaved: @escaping (LedgerTransaction) -> Void
    ) {
        _model = State(initialValue: AddTransactionViewModel(repository: repository, editing: editing))
        self.onSaved = onSaved
    }

    var body: some View {
        NavigationStack {
            RemoteContentView(content: model.reference, retry: { Task { await model.load() } }) { reference in
                if model.isLockedSplit {
                    EmptyStateView(
                        title: "edit.split.title",
                        systemImage: "square.split.2x1",
                        message: "edit.split.message"
                    )
                } else if reference.accounts.isEmpty {
                    EmptyStateView(
                        title: "add.noAccounts.title",
                        systemImage: "creditcard",
                        message: "add.noAccounts.message"
                    )
                } else {
                    form
                }
            }
            .navigationTitle(Text(model.isNew ? LocalizedStringKey("add.title") : LocalizedStringKey("edit.title")))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("action.cancel") { dismiss() }
                        .disabled(model.isSaving)
                }
                ToolbarItem(placement: .confirmationAction) {
                    if model.isSaving {
                        ProgressView()
                            .accessibilityLabel(Text("add.saving"))
                    } else {
                        Button("action.save") { save() }
                            .fontWeight(.semibold)
                            .disabled(!model.reference.hasValue || model.accounts.isEmpty || model.isLockedSplit)
                    }
                }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("action.done") { focusedField = nil }
                }
            }
            .task { await model.loadIfNeeded() }
        }
        .interactiveDismissDisabled(model.isSaving)
    }

    private var form: some View {
        @Bindable var model = model
        return Form {
            Section {
                Picker(selection: $model.kind) {
                    Text("type.expense").tag(TransactionKind.expense)
                    Text("type.income").tag(TransactionKind.income)
                    Text("type.transfer").tag(TransactionKind.transfer)
                } label: {
                    Text("add.type")
                }
                .pickerStyle(.segmented)
                .onChange(of: model.kind) {
                    model.kindDidChange()
                }
            }

            Section {
                Picker(selection: $model.accountID) {
                    ForEach(model.accounts) { account in
                        Text(account.name + " (" + account.currency.uppercased() + ")")
                            .tag(Optional(account.id))
                    }
                } label: {
                    Text(model.kind == .transfer ? LocalizedStringKey("add.fromAccount") : LocalizedStringKey("add.account"))
                }
                .onChange(of: model.accountID) {
                    model.accountDidChange()
                }
                fieldError(model.accountError)

                amountField(
                    title: model.isForeignCurrency && !model.accountCurrency.isEmpty
                        ? L10n.format("add.amountDebited", model.accountCurrency)
                        : L10n.format("add.amount", model.accountCurrency),
                    text: $model.amountText,
                    field: .amount
                )
                fieldError(model.amountError)
            }

            if model.kind == .transfer {
                transferSection
            } else {
                foreignCurrencySection
            }

            Section {
                if model.kind != .transfer {
                    Picker(selection: $model.categoryID) {
                        Text("add.noCategory").tag(Int?.none)
                        ForEach(model.categoryOptions) { option in
                            Text(option.title).tag(Optional(option.id))
                        }
                    } label: {
                        Text("add.category")
                    }
                    .pickerStyle(.navigationLink)
                }

                DatePicker(selection: $model.date, displayedComponents: .date) {
                    Text("add.date")
                }

                TextField("add.description", text: $model.descriptionText, axis: .vertical)
                    .lineLimit(1...4)
                    .focused($focusedField, equals: .description)
                fieldError(model.descriptionError)
            }

            if let error = model.saveError {
                Section {
                    Label {
                        Text(error)
                    } icon: {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(Theme.negative)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
    }

    /// Destination account and, between currencies, the credited amount.
    private var transferSection: some View {
        @Bindable var model = model
        return Section {
            Picker(selection: $model.transferAccountID) {
                Text("add.chooseAccount").tag(Int?.none)
                ForEach(model.destinationOptions) { account in
                    Text(account.name + " (" + account.currency.uppercased() + ")")
                        .tag(Optional(account.id))
                }
            } label: {
                Text("add.toAccount")
            }
            .onChange(of: model.transferAccountID) {
                model.transferAmountText = ""
            }
            fieldError(model.destinationError)

            if model.isCrossCurrencyTransfer {
                amountField(
                    title: L10n.format("add.amountCredited", model.destinationCurrency),
                    text: $model.transferAmountText,
                    field: .transferAmount
                )
                fieldError(model.transferAmountError)
            }
        } footer: {
            if model.isCrossCurrencyTransfer {
                Text("add.transfer.crossFooter")
            } else {
                Text("add.transfer.footer")
            }
        }
    }

    private var foreignCurrencySection: some View {
        @Bindable var model = model
        return Section {
            Toggle(isOn: $model.isForeignCurrency.animation()) {
                Text("add.foreign")
            }
            if model.isForeignCurrency {
                TextField("add.currencyCode", text: $model.currencyCode)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                    .focused($focusedField, equals: .currency)
                    .onChange(of: model.currencyCode) {
                        let cleaned = String(model.currencyCode.uppercased().prefix(3))
                        if cleaned != model.currencyCode {
                            model.currencyCode = cleaned
                        }
                    }
                fieldError(model.currencyError)

                amountField(
                    title: L10n.format("add.amountPaid", model.currencyCode.isEmpty ? "…" : model.currencyCode),
                    text: $model.foreignAmountText,
                    field: .foreignAmount
                )
                fieldError(model.foreignAmountError)
            }
        } footer: {
            if model.isForeignCurrency {
                Text("add.foreign.footer")
            }
        }
    }

    private func amountField(title: String, text: Binding<String>, field: Field) -> some View {
        LabeledContent {
            TextField("0", text: text)
                .keyboardType(.decimalPad)
                .multilineTextAlignment(.trailing)
                .font(.body.monospacedDigit())
                .focused($focusedField, equals: field)
                .accessibilityLabel(Text(title))
        } label: {
            Text(title)
        }
    }

    @ViewBuilder
    private func fieldError(_ message: String?) -> some View {
        if let message {
            Text(message)
                .font(.footnote)
                .foregroundStyle(Theme.negative)
        }
    }

    private func save() {
        focusedField = nil
        Task {
            if let saved = await model.save() {
                onSaved(saved)
                dismiss()
            }
        }
    }
}
