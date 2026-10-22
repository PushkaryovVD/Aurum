import SwiftUI

/// The finance shell, shared by both storage modes: one NavigationStack per
/// tab, every screen working through the repository protocols only.
struct MainTabView: View {
    let repository: any FinanceRepository
    /// Server viewers cannot write; the device ledger always can.
    let canEdit: Bool
    /// Set in "Only on iPhone" mode: settings and backup in "More".
    let local: LocalRepository?

    var body: some View {
        TabView {
            DashboardView(repository: repository)
                .tabItem {
                    Label("tab.overview", systemImage: "chart.pie")
                }

            TransactionsView(repository: repository, canEdit: canEdit)
                .tabItem {
                    Label("tab.transactions", systemImage: "list.bullet.rectangle")
                }

            AccountsView(repository: repository, canEdit: canEdit)
                .tabItem {
                    Label("tab.accounts", systemImage: "creditcard")
                }

            MoreView(local: local)
                .tabItem {
                    Label("tab.more", systemImage: "ellipsis.circle")
                }
        }
    }
}
