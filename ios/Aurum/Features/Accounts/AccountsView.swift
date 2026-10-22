import SwiftUI

/// "Accounts": every active account (archived ones on request) with its live
/// balance, grouped by currency with a per-currency subtotal. Tapping an
/// account edits it; "+" adds one (both modes, editors only).
struct AccountsView: View {
    @State private var model: AccountsViewModel
    @State private var editor: EditorTarget?
    @State private var showArchived = false
    private let repository: any FinanceRepository
    private let events: LedgerEvents
    private let canEdit: Bool

    /// Which account the editor sheet is open for (nil account = new one).
    private struct EditorTarget: Identifiable {
        let account: AccountWithBalance?
        var id: Int { account?.id ?? -1 }
    }

    init(repository: any FinanceRepository, canEdit: Bool) {
        _model = State(initialValue: AccountsViewModel(repository: repository))
        self.repository = repository
        self.events = repository.events
        self.canEdit = canEdit
    }

    var body: some View {
        NavigationStack {
            RemoteContentView(content: model.accounts, retry: { Task { await model.load() } }) { accounts in
                if accounts.isEmpty {
                    List {
                        EmptyStateView(
                            title: "accounts.empty.title",
                            systemImage: "creditcard",
                            message: "accounts.empty.message"
                        )
                        .listRowBackground(Color.clear)
                    }
                    .refreshable { await model.load() }
                } else {
                    accountList(accounts)
                }
            }
            .navigationTitle(Text("tab.accounts"))
            .toolbar { toolbar }
            .sheet(item: $editor) { target in
                AccountEditorView(
                    repository: repository,
                    account: target.account,
                    // A new device account starts in the Overview's currency.
                    defaultCurrency: (repository as? LocalRepository)?.reportingCurrency
                        ?? LocalRepository.defaultReportingCurrency
                )
            }
            .task { await model.loadIfNeeded() }
            .onChange(of: events.revision) {
                Task { await model.load() }
            }
            .onChange(of: showArchived) {
                Task { await model.setShowsArchived(showArchived) }
            }
        }
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        ToolbarItem(placement: .topBarLeading) {
            Menu {
                Toggle(isOn: $showArchived) {
                    Label("accounts.showArchived", systemImage: "archivebox")
                }
            } label: {
                Image(systemName: "line.3.horizontal.decrease.circle")
                    .frame(minWidth: 44, minHeight: 44)
            }
            .accessibilityLabel(Text("accounts.filter"))
        }
        // Viewers cannot write (the API answers 403), so no add button.
        ToolbarItem(placement: .primaryAction) {
            if canEdit {
                Button {
                    editor = EditorTarget(account: nil)
                } label: {
                    Image(systemName: "plus")
                }
                .accessibilityLabel(Text("accounts.add"))
            }
        }
    }

    private func accountList(_ accounts: [AccountWithBalance]) -> some View {
        List {
            if model.accounts.isStale, let error = model.accounts.error {
                StaleDataBanner(message: error, updatedAt: model.accounts.updatedAt) {
                    Task { await model.load() }
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
            }

            ForEach(AccountsViewModel.groups(accounts)) { group in
                Section {
                    ForEach(group.accounts) { account in
                        if canEdit {
                            Button {
                                editor = EditorTarget(account: account)
                            } label: {
                                AccountRow(account: account)
                            }
                            .tint(.primary)
                            .accessibilityHint(Text("accounts.editHint"))
                        } else {
                            AccountRow(account: account)
                        }
                    }
                } header: {
                    Text(group.currency)
                } footer: {
                    HStack {
                        Text("accounts.total")
                        Spacer()
                        Text(Money.format(group.total, currency: group.currency))
                            .monospacedDigit()
                    }
                    .font(.footnote.weight(.semibold))
                    .accessibilityElement(children: .combine)
                }
            }
        }
        .listStyle(.insetGrouped)
        .refreshable { await model.load() }
    }
}

private struct AccountRow: View {
    let account: AccountWithBalance

    private var symbol: String {
        switch account.type {
        case "cash": return "banknote"
        case "savings": return "building.columns"
        case "credit_card": return "creditcard.fill"
        case "debit_card": return "creditcard"
        case "investment": return "chart.line.uptrend.xyaxis"
        case "checking": return "wallet.pass"
        default: return "circle.grid.2x2"
        }
    }

    private var subtitle: String {
        let type = L10n.text("account.type.\(account.type)", fallback: account.type)
        return account.isArchived ? type + " · " + L10n.text("accounts.archived") : type
    }

    var body: some View {
        HStack(spacing: Theme.Spacing.m) {
            Image(systemName: symbol)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Color(hex: account.color) ?? .accentColor)
                .frame(width: 36, height: 36)
                .background((Color(hex: account.color) ?? .accentColor).opacity(0.15), in: Circle())
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 2) {
                Text(account.name)
                    .font(.body)
                    .lineLimit(2)
                Text(subtitle)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Spacer(minLength: Theme.Spacing.s)

            Text(Money.format(account.balance, currency: account.currency))
                .font(.body.weight(.semibold).monospacedDigit())
                .foregroundStyle(account.balance.value < 0 ? Theme.negative : Theme.expense)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }
}
