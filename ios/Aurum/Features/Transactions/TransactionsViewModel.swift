import Foundation
import Observation

/// Paged, filterable list of operations (GET /api/transactions).
@MainActor
@Observable
final class TransactionsViewModel {
    static let pageSize = 50

    /// The filter whose results are (being) shown.
    private(set) var filter = TransactionFilter(month: MonthRef.current(), search: "")
    private(set) var list = RemoteContent<[LedgerTransaction]>()
    private(set) var total = 0
    private(set) var isLoadingMore = false
    /// A failed "next page" is reported under the list, not as a full-screen
    /// error — the rows already loaded stay valid.
    private(set) var loadMoreError: String?

    private let client: APIClient
    private var loadedPages = 0
    private var generation = 0

    init(client: APIClient) {
        self.client = client
    }

    var hasMore: Bool {
        guard let items = list.value else { return false }
        return items.count < total
    }

    /// Rows grouped by calendar day, newest first (the API already sorts).
    var sections: [DaySection] {
        guard let items = list.value else { return [] }
        var result: [DaySection] = []
        for item in items {
            if let last = result.last, last.date == item.date {
                result[result.count - 1].items.append(item)
            } else {
                result.append(DaySection(date: item.date, items: [item]))
            }
        }
        return result
    }

    // MARK: - Loading

    /// Applies a new filter. A changed filter drops the old rows: results
    /// for a different month/search must never be shown under the new one.
    func apply(_ newFilter: TransactionFilter) async {
        if newFilter == filter, list.hasValue || list.isLoading { return }
        if newFilter != filter {
            filter = newFilter
            list.reset()
            total = 0
        }
        await reload()
    }

    /// Reloads page 1 for the current filter (pull-to-refresh, retry, after
    /// adding an operation). Keeps current rows visible until it succeeds.
    func reload() async {
        generation += 1
        let token = generation
        let requested = filter
        list.beginLoading()
        loadMoreError = nil
        do {
            let page = try await client.transactions(requested, page: 1, pageSize: Self.pageSize)
            guard token == generation else { return }
            total = page.total
            loadedPages = 1
            list.succeed(page.items)
        } catch {
            guard token == generation else { return }
            if error.isCancellation {
                list.cancel()
            } else {
                list.fail(error.displayMessage)
            }
        }
    }

    func loadMore() async {
        guard hasMore, !isLoadingMore, !list.isLoading, let current = list.value else { return }
        let token = generation
        let requested = filter
        let nextPage = loadedPages + 1
        isLoadingMore = true
        loadMoreError = nil
        defer { isLoadingMore = false }
        do {
            let page = try await client.transactions(requested, page: nextPage, pageSize: Self.pageSize)
            guard token == generation else { return }
            // Rows can shift between pages if something was added meanwhile;
            // never show the same operation twice.
            let known = Set(current.map(\.id))
            let fresh = page.items.filter { !known.contains($0.id) }
            total = page.total
            loadedPages = nextPage
            list.succeed(current + fresh)
        } catch {
            guard token == generation, !error.isCancellation else { return }
            loadMoreError = error.displayMessage
        }
    }
}

struct DaySection: Identifiable {
    /// "YYYY-MM-DD"
    let date: String
    var items: [LedgerTransaction]

    var id: String { date }
}
