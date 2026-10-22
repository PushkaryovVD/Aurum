import SwiftUI

/// Sheet for recording an income or expense.
struct AddTransactionView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var model: AddTransactionViewModel
    @FocusState private var focusedField: Field?

    private let onSaved: () -> Void

    private enum Field: Hashable {
        case amount
        case currency
        case foreignAmount
        case description
    }

    init(client: APIClient, onSaved: @escaping () -> Void) {
        _model = State(initialValue: AddTransactionViewModel(client: client))
        self.onSaved = onSaved
    }

    var body: some View {
        NavigationStack {
            RemoteContentView(content: model.reference, retry: { Task { await model.load() } }) { reference in
                if reference.accounts.isEmpty {
                    EmptyStateView(
                        title: "add.noAccounts.title",
                        systemImage: "creditcard",
                        message: "add.noAccounts.message"
                    )
                } else {
                    form
                }
            }
            .navigationTitle(Text("add.title"))
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
                            .disabled(!model.reference.hasValue || model.accounts.isEmpty)
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
                    Text("add.account")
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

            Section {
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

            Section {
                Picker(selection: $model.categoryID) {
                    Text("add.noCategory").tag(Int?.none)
                    ForEach(model.categoryOptions) { option in
                        Text(option.title).tag(Optional(option.id))
                    }
                } label: {
                    Text("add.category")
                }
                .pickerStyle(.navigationLink)

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
            if await model.save() {
                onSaved()
                dismiss()
            }
        }
    }
}
