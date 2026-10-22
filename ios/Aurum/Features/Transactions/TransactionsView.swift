import SwiftUI

/// "Operations": month-filtered, searchable, paged list with pull-to-refresh.
struct TransactionsView: View {
    let client: APIClient
    let canEdit: Bool

    @State private var model: TransactionsViewModel
    @State private var month: MonthRef? = MonthRef.current()
    @State private var searchText = ""
    @State private var isAdding = false

    init(client: APIClient, canEdit: Bool) {
        self.client = client
        self.canEdit = canEdit
        _model = State(initialValue: TransactionsViewModel(client: client))
    }

    private var requestedFilter: TransactionFilter {
        TransactionFilter(month: month, search: searchText)
    }

    var body: some View {
        NavigationStack {
            content
                .navigationTitle(Text("tab.transactions"))
                .navigationDestination(for: LedgerTransaction.self) { transaction in
                    TransactionDetailView(transaction: transaction)
                }
                .searchable(text: $searchText, prompt: Text("transactions.search"))
                .safeAreaInset(edge: .top, spacing: 0) {
                    filterBar
                }
                .toolbar {
                    // Viewers cannot write (the API answers 403), so the
                    // add button is not offered to them at all.
                    ToolbarItem(placement: .primaryAction) {
                        if canEdit {
                            Button {
                                isAdding = true
                            } label: {
                                Image(systemName: "plus")
                            }
                            .accessibilityLabel(Text("transactions.add"))
                        }
                    }
                }
                .sheet(isPresented: $isAdding) {
                    AddTransactionView(client: client) {
                        Task { await model.reload() }
                    }
                }
                .task(id: requestedFilter) {
                    // Debounce typing: only a changed search waits; month
                    // switches and the first load go out immediately.
                    if requestedFilter.search != model.filter.search {
                        try? await Task.sleep(for: .milliseconds(350))
                        if Task.isCancelled { return }
                    }
                    await model.apply(requestedFilter)
                }
        }
    }

    @ViewBuilder
    private var content: some View {
        if let items = model.list.value {
            if items.isEmpty && !model.list.isStale {
                List {
                    emptyState
                        .listRowBackground(Color.clear)
                }
                .refreshable { await model.reload() }
            } else {
                list
            }
        } else if let error = model.list.error {
            ErrorStateView(message: error) {
                Task { await model.reload() }
            }
        } else {
            LoadingStateView()
        }
    }

    private var list: some View {
        List {
            if model.list.isStale, let error = model.list.error {
                StaleDataBanner(message: error, updatedAt: model.list.updatedAt) {
                    Task { await model.reload() }
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
            }

            ForEach(model.sections) { section in
                Section {
                    ForEach(section.items) { transaction in
                        NavigationLink(value: transaction) {
                            TransactionRow(transaction: transaction)
                        }
                    }
                } header: {
                    Text(APIDate.sectionTitle(section.date))
                }
            }

            pagingFooter
        }
        .listStyle(.insetGrouped)
        .refreshable { await model.reload() }
    }

    @ViewBuilder
    private var pagingFooter: some View {
        if let error = model.loadMoreError {
            Section {
                VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Button("action.retry") {
                        Task { await model.loadMore() }
                    }
                }
            }
        } else if model.hasMore {
            Section {
                HStack {
                    Spacer()
                    ProgressView()
                        .accessibilityLabel(Text("transactions.loadingMore"))
                    Spacer()
                }
                .onAppear {
                    Task { await model.loadMore() }
                }
            }
        } else if let items = model.list.value, !items.isEmpty {
            Section {
                Text(L10n.format("transactions.count", String(model.total)))
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
            }
            .listRowBackground(Color.clear)
        }
    }

    @ViewBuilder
    private var emptyState: some View {
        if !searchText.trimmingCharacters(in: .whitespaces).isEmpty {
            ContentUnavailableView.search(text: searchText)
        } else {
            EmptyStateView(
                title: "transactions.empty.title",
                systemImage: "tray",
                message: month == nil
                    ? LocalizedStringKey("transactions.empty.all")
                    : LocalizedStringKey("transactions.empty.month")
            )
        }
    }

    /// Month filter: ‹ month › plus an "all time" switch.
    private var filterBar: some View {
        HStack(spacing: Theme.Spacing.s) {
            if let month {
                MonthSwitcher(
                    month: month,
                    canGoForward: !month.isCurrentOrFuture,
                    previous: { self.month = month.previous },
                    next: { self.month = month.next }
                )
            } else {
                Text("transactions.allTime")
                    .font(.headline)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(Theme.cardBackground, in: RoundedRectangle(cornerRadius: Theme.Radius.card))
            }

            Menu {
                Button {
                    month = MonthRef.current()
                } label: {
                    Label("transactions.filter.thisMonth", systemImage: "calendar")
                }
                Button {
                    month = nil
                } label: {
                    Label("transactions.filter.allTime", systemImage: "infinity")
                }
            } label: {
                Image(systemName: "line.3.horizontal.decrease.circle")
                    .font(.title3)
                    .frame(minWidth: 44, minHeight: 44)
            }
            .accessibilityLabel(Text("transactions.filter"))
        }
        .padding(.horizontal, Theme.Spacing.l)
        .padding(.vertical, Theme.Spacing.s)
        .background(.bar)
    }
}
