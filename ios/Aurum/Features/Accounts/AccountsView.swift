import SwiftUI

/// "Accounts": every active account with its live balance, grouped by
/// currency with a per-currency subtotal.
struct AccountsView: View {
    @State private var model: AccountsViewModel

    init(client: APIClient) {
        _model = State(initialValue: AccountsViewModel(client: client))
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
            .task { await model.loadIfNeeded() }
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
                        AccountRow(account: account)
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
                Text(L10n.text("account.type.\(account.type)", fallback: account.type))
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
