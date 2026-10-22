import Foundation
import Observation

@MainActor
@Observable
final class DashboardViewModel {
    private(set) var month = MonthRef.current()
    private(set) var summary = RemoteContent<DashboardSummary>()

    private let client: APIClient
    /// Guards against an older month's response landing after a newer one.
    private var generation = 0

    init(client: APIClient) {
        self.client = client
    }

    var canGoForward: Bool { !month.isCurrentOrFuture }

    func loadIfNeeded() async {
        guard !summary.hasValue, !summary.isLoading else { return }
        await load()
    }

    func load() async {
        generation += 1
        let token = generation
        let requested = month
        summary.beginLoading()
        do {
            let result = try await client.dashboardSummary(month: requested)
            guard token == generation else { return }
            summary.succeed(result)
        } catch {
            guard token == generation else { return }
            if error.isCancellation {
                summary.cancel()
            } else {
                summary.fail(error.displayMessage)
            }
        }
    }

    func showPreviousMonth() async {
        month = month.previous
        // A different month's numbers must not stay on screen under the new
        // month's title, so the old value is dropped rather than kept stale.
        summary.reset()
        await load()
    }

    func showNextMonth() async {
        guard canGoForward else { return }
        month = month.next
        summary.reset()
        await load()
    }
}
