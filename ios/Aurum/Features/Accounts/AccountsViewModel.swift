import Foundation
import Observation

@MainActor
@Observable
final class AccountsViewModel {
    private(set) var accounts = RemoteContent<[AccountWithBalance]>()

    private let client: APIClient
    private var generation = 0

    init(client: APIClient) {
        self.client = client
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
            let result = try await client.accounts()
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
