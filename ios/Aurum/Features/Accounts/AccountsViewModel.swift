import Foundation
import Observation

@MainActor
@Observable
final class AccountsViewModel {
    private(set) var accounts = RemoteContent<[AccountWithBalance]>()
    /// Archived accounts are hidden unless asked for (they still count in
    /// the Overview's total balance, as on the server).
    private(set) var showsArchived = false

    private let repository: any AccountRepository
    private var generation = 0

    init(repository: any AccountRepository) {
        self.repository = repository
    }

    func loadIfNeeded() async {
        guard !accounts.hasValue, !accounts.isLoading else { return }
        await load()
    }

    func load() async {
        generation += 1
        let token = generation
        accounts.beginLoading()
        do {
            let result = try await repository.accounts(includeArchived: showsArchived)
            guard token == generation else { return }
            accounts.succeed(result)
        } catch {
            guard token == generation else { return }
            if error.isCancellation {
                accounts.cancel()
            } else {
                accounts.fail(error.displayMessage)
            }
        }
    }

    func setShowsArchived(_ value: Bool) async {
        guard value != showsArchived else { return }
        showsArchived = value
        await load()
    }

    /// Accounts grouped by currency — balances in different currencies are
    /// never added together here; the dashboard does the rate conversion.
    static func groups(_ accounts: [AccountWithBalance]) -> [CurrencyGroup] {
        var order: [String] = []
        var byCurrency: [String: [AccountWithBalance]] = [:]
        for account in accounts {
            let code = account.currency.uppercased()
            if byCurrency[code] == nil {
                order.append(code)
            }
            byCurrency[code, default: []].append(account)
        }
        return order.map { code in
            let items = byCurrency[code] ?? []
            let total = items.reduce(Decimal(0)) { $0 + $1.balance.value }
            return CurrencyGroup(currency: code, accounts: items, total: total)
        }
    }
}

struct CurrencyGroup: Identifiable, Sendable {
    let currency: String
    let accounts: [AccountWithBalance]
    let total: Decimal

    var id: String { currency }
}
