import SwiftUI

/// The signed-in shell: one NavigationStack per tab.
struct MainTabView: View {
    let client: APIClient
    let workspace: WorkspaceSummary

    var body: some View {
        TabView {
            DashboardView(client: client)
                .tabItem {
                    Label("tab.overview", systemImage: "chart.pie")
                }

            TransactionsView(client: client, canEdit: workspace.canEdit)
                .tabItem {
                    Label("tab.transactions", systemImage: "list.bullet.rectangle")
                }

            AccountsView(client: client)
                .tabItem {
                    Label("tab.accounts", systemImage: "creditcard")
                }

            MoreView()
                .tabItem {
                    Label("tab.more", systemImage: "ellipsis.circle")
                }
        }
    }
}
