import SwiftUI

/// "Overview": the month's real income/spending, the all-time balance and
/// the biggest spending categories.
struct DashboardView: View {
    @State private var model: DashboardViewModel
    private let events: LedgerEvents

    init(repository: any FinanceRepository) {
        _model = State(initialValue: DashboardViewModel(repository: repository))
        events = repository.events
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                    MonthSwitcher(
                        month: model.month,
                        canGoForward: model.canGoForward,
                        previous: { Task { await model.showPreviousMonth() } },
                        next: { Task { await model.showNextMonth() } }
                    )

                    if model.summary.isStale, let error = model.summary.error {
                        StaleDataBanner(message: error, updatedAt: model.summary.updatedAt) {
                            Task { await model.load() }
                        }
                    }

                    RemoteContentView(content: model.summary, retry: { Task { await model.load() } }) { summary in
                        DashboardContent(summary: summary)
                    }
                    .frame(minHeight: model.summary.hasValue ? nil : 320)
                }
                .padding(.horizontal, Theme.Spacing.l)
                .padding(.vertical, Theme.Spacing.m)
            }
            .background(Theme.groupedBackground)
            .navigationTitle(Text("tab.overview"))
            .refreshable { await model.load() }
            .task { await model.loadIfNeeded() }
            // An operation added/edited/deleted on another tab changes this
            // month's numbers; refresh instead of showing outdated totals.
            .onChange(of: events.revision) {
                Task { await model.load() }
            }
        }
    }
}

/// Previous / next month with the month's name between. Large hit targets.
struct MonthSwitcher: View {
    let month: MonthRef
    let canGoForward: Bool
    let previous: () -> Void
    let next: () -> Void

    var body: some View {
        HStack {
            Button(action: previous) {
                Image(systemName: "chevron.left")
                    .frame(minWidth: 44, minHeight: 44)
            }
            .accessibilityLabel(Text("month.previous"))

            Spacer()
            Text(month.title)
                .font(.headline)
                .accessibilityAddTraits(.isHeader)
            Spacer()

            Button(action: next) {
                Image(systemName: "chevron.right")
                    .frame(minWidth: 44, minHeight: 44)
            }
            .disabled(!canGoForward)
            .accessibilityLabel(Text("month.next"))
        }
        .padding(.horizontal, Theme.Spacing.xs)
        .background(Theme.cardBackground, in: RoundedRectangle(cornerRadius: Theme.Radius.card))
    }
}

private struct DashboardContent: View {
    let summary: DashboardSummary

    private var reportingCurrency: String { summary.balance.reportingCurrency }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l) {
            BalanceCard(balance: summary.balance)

            ViewThatFits(in: .horizontal) {
                HStack(spacing: Theme.Spacing.m) { metricCards }
                VStack(spacing: Theme.Spacing.m) { metricCards }
            }

            if let excluded = summary.excludedCurrencies, !excluded.isEmpty {
                Label {
                    Text(L10n.format("dashboard.excludedCurrencies", excluded.joined(separator: ", ")))
                } icon: {
                    Image(systemName: "exclamationmark.circle")
                }
                .font(.footnote)
                .foregroundStyle(.orange)
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            SpendingCard(items: summary.spendingByCategory, currency: reportingCurrency)
        }
    }

    @ViewBuilder
    private var metricCards: some View {
        MetricCard(
            title: "dashboard.income",
            value: Money.format(summary.realIncome, currency: reportingCurrency),
            tint: Theme.income
        )
        MetricCard(
            title: "dashboard.spent",
            value: Money.format(summary.spent, currency: reportingCurrency),
            tint: Theme.expense
        )
        MetricCard(
            title: "dashboard.net",
            value: Money.format(summary.net, currency: reportingCurrency),
            tint: summary.net.value < 0 ? Theme.negative : Theme.income
        )
    }
}

private struct MetricCard: View {
    let title: LocalizedStringKey
    let value: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Text(title)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.weight(.semibold).monospacedDigit())
                .foregroundStyle(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Theme.Spacing.m)
        .background(Theme.cardBackground, in: RoundedRectangle(cornerRadius: Theme.Radius.card))
        .accessibilityElement(children: .combine)
    }
}

private struct BalanceCard: View {
    let balance: BalanceSummary

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            Text("dashboard.balance")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text(Money.format(balance.total, currency: balance.reportingCurrency))
                .font(.largeTitle.weight(.bold).monospacedDigit())
                .lineLimit(1)
                .minimumScaleFactor(0.5)
                .accessibilityAddTraits(.isHeader)

            if balance.incomplete {
                Label("dashboard.balance.incomplete", systemImage: "exclamationmark.circle")
                    .font(.footnote)
                    .foregroundStyle(.orange)
            }

            // Per-currency breakdown only when there is more than one currency.
            if balance.items.count > 1 {
                Divider()
                ForEach(balance.items, id: \.currency) { item in
                    HStack(alignment: .firstTextBaseline) {
                        Text(Money.format(item.amount, currency: item.currency))
                            .font(.subheadline.monospacedDigit())
                        Spacer()
                        if let reporting = item.amountReporting {
                            Text(Money.format(reporting, currency: balance.reportingCurrency))
                                .font(.footnote.monospacedDigit())
                                .foregroundStyle(.secondary)
                        } else {
                            Text("dashboard.balance.noRate")
                                .font(.footnote)
                                .foregroundStyle(.orange)
                        }
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Theme.Spacing.l)
        .background(Theme.cardBackground, in: RoundedRectangle(cornerRadius: Theme.Radius.card))
    }
}

private struct SpendingCard: View {
    let items: [CategoryBreakdownItem]
    let currency: String

    private var topItems: [CategoryBreakdownItem] { Array(items.prefix(6)) }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            Text("dashboard.topCategories")
                .font(.headline)
                .accessibilityAddTraits(.isHeader)

            if topItems.isEmpty {
                Text("dashboard.noSpending")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(topItems.enumerated()), id: \.offset) { _, item in
                    CategoryShareRow(item: item, currency: currency)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Theme.Spacing.l)
        .background(Theme.cardBackground, in: RoundedRectangle(cornerRadius: Theme.Radius.card))
    }
}

private struct CategoryShareRow: View {
    let item: CategoryBreakdownItem
    let currency: String

    private var fraction: Double { min(max(item.percent / 100, 0), 1) }
    private var tint: Color { Color(hex: item.color) ?? .accentColor }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            HStack(alignment: .firstTextBaseline) {
                Circle()
                    .fill(tint)
                    .frame(width: 10, height: 10)
                    .accessibilityHidden(true)
                Text(CategoryNames.display(item.name))
                    .font(.subheadline)
                    .lineLimit(2)
                Spacer(minLength: Theme.Spacing.s)
                Text(Money.format(item.amount, currency: currency))
                    .font(.subheadline.monospacedDigit())
            }
            ProgressView(value: fraction)
                .tint(tint)
                .accessibilityHidden(true)
            Text(item.percent.formatted(.number.precision(.fractionLength(0...1))) + "%")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }
}
