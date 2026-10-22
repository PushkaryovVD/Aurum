import SwiftUI

/// Sheet for adding or editing an account (name, type, currency, archive
/// and — on the device only — the opening balance).
struct AccountEditorView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var model: AccountEditorViewModel
    @FocusState private var focusedField: Field?

    private enum Field: Hashable {
        case name
        case currency
        case balance
    }

    init(repository: any AccountRepository, account: AccountWithBalance?, defaultCurrency: String = LocalRepository.defaultReportingCurrency) {
        _model = State(initialValue: AccountEditorViewModel(
            repository: repository,
            account: account,
            defaultCurrency: defaultCurrency
        ))
    }

    var body: some View {
        @Bindable var model = model
        NavigationStack {
            Form {
                Section {
                    TextField("account.name", text: $model.name)
                        .focused($focusedField, equals: .name)
                        .submitLabel(.done)
                    fieldError(model.nameError)

                    Picker(selection: $model.kind) {
                        ForEach(AccountKind.allCases) { kind in
                            Text(L10n.text("account.type.\(kind.rawValue)", fallback: kind.rawValue)).tag(kind)
                        }
                    } label: {
                        Text("account.type")
                    }
                }

                Section {
                    TextField("add.currencyCode", text: $model.currency)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .focused($focusedField, equals: .currency)
                        .disabled(model.isCurrencyLocked)
                        .onChange(of: model.currency) {
                            let cleaned = String(model.currency.uppercased().prefix(3))
                            if cleaned != model.currency {
                                model.currency = cleaned
                            }
                        }
                    fieldError(model.currencyError)
                } header: {
                    Text("account.currency")
                } footer: {
                    if model.isCurrencyLocked {
                        Text("account.currency.locked")
                    }
                }

                if model.supportsInitialBalance {
                    Section {
                        LabeledContent {
                            TextField("0", text: $model.initialBalanceText)
                                .keyboardType(.numbersAndPunctuation)
                                .multilineTextAlignment(.trailing)
                                .font(.body.monospacedDigit())
                                .focused($focusedField, equals: .balance)
                                .accessibilityLabel(Text("account.initialBalance"))
                        } label: {
                            Text("account.initialBalance")
                        }
                        fieldError(model.initialBalanceError)
                    } footer: {
                        Text("account.initialBalance.footer")
                    }
                }

                if !model.isNew {
                    Section {
                        Toggle(isOn: $model.isArchived) {
                            Text("account.archived")
                        }
                    } footer: {
                        Text("account.archived.footer")
                    }
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
            .navigationTitle(Text(model.isNew ? LocalizedStringKey("account.new") : LocalizedStringKey("account.edit")))
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
                    }
                }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("action.done") { focusedField = nil }
                }
            }
        }
        .interactiveDismissDisabled(model.isSaving)
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
                dismiss()
            }
        }
    }
}
