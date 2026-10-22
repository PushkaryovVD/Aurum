import Foundation

/// Display names for categories. The default set is stored under the
/// server's English names (backend/app/db/seed.py) in both modes; this maps
/// exactly those names to localized strings, the same way the web app's
/// frontend/src/lib/categoryLabels.ts does. Anything the user named
/// themselves is shown as typed.
enum CategoryNames {
    private static let keys: [String: String] = [
        "Housing & Utilities": "category.housingUtilities",
        "Groceries": "category.groceries",
        "Dining Out": "category.diningOut",
        "Transportation": "category.transportation",
        "Health & Fitness": "category.healthFitness",
        "Shopping": "category.shopping",
        "Entertainment": "category.entertainment",
        "Subscriptions": "category.subscriptions",
        "Salary": "category.salary",
        "Freelance": "category.freelance",
        "Investments": "category.investments",
        "Gifts": "category.gifts",
        "Business Income": "category.businessIncome",
        "Rental Income": "category.rentalIncome",
        "Benefits": "category.benefits",
        "Item Sales": "category.itemSales",
        "Other Income": "category.otherIncome",
        // The server's dashboard names its overflow slice "Other".
        "Other": "dashboard.other",
    ]

    static func display(_ name: String) -> String {
        guard let key = keys[name] else { return name }
        return L10n.text(key, fallback: name)
    }
}
