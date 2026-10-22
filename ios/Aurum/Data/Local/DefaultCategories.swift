import Foundation

/// The starter categories of the on-device ledger — the exact set, names,
/// icons, colors and order the server seeds for a new workspace
/// (backend/app/db/seed.py). Names stay in English on purpose, like on the
/// server: CategoryNames translates them for display, and a backup carried
/// to the server lines up with the server's own defaults.
enum DefaultCategories {
    struct Seed: Sendable, Hashable {
        let name: String
        let icon: String
        let color: String
        /// "income" | "expense"
        let kind: String
    }

    /// Expense first, then income; the position doubles as sort_order.
    static let all: [Seed] = expense + income

    static let expense: [Seed] = [
        Seed(name: "Housing & Utilities", icon: "home", color: "#2a78d6", kind: "expense"),
        Seed(name: "Groceries", icon: "shopping-basket", color: "#1baf7a", kind: "expense"),
        Seed(name: "Dining Out", icon: "utensils", color: "#eb6834", kind: "expense"),
        Seed(name: "Transportation", icon: "car", color: "#4a3aa7", kind: "expense"),
        Seed(name: "Health & Fitness", icon: "heart-pulse", color: "#e34948", kind: "expense"),
        Seed(name: "Shopping", icon: "shopping-bag", color: "#eda100", kind: "expense"),
        Seed(name: "Entertainment", icon: "clapperboard", color: "#e87ba4", kind: "expense"),
        Seed(name: "Subscriptions", icon: "repeat", color: "#008300", kind: "expense"),
    ]

    static let income: [Seed] = [
        Seed(name: "Salary", icon: "banknote", color: "#2a78d6", kind: "income"),
        Seed(name: "Freelance", icon: "briefcase", color: "#1baf7a", kind: "income"),
        Seed(name: "Investments", icon: "trending-up", color: "#4a3aa7", kind: "income"),
        Seed(name: "Gifts", icon: "gift", color: "#e87ba4", kind: "income"),
        Seed(name: "Business Income", icon: "building-2", color: "#eb6834", kind: "income"),
        Seed(name: "Rental Income", icon: "key", color: "#eda100", kind: "income"),
        Seed(name: "Benefits", icon: "hand-coins", color: "#008300", kind: "income"),
        Seed(name: "Item Sales", icon: "tag", color: "#e34948", kind: "income"),
        Seed(name: "Other Income", icon: "plus-circle", color: "#898781", kind: "income"),
    ]

    /// The server's starter account (seed.py add_workspace_defaults) has
    /// the same type and color; its name is localized here because, unlike
    /// a category name, an account name is the user's own text from then on.
    static let starterAccountColor = "#2a78d6"
    static let starterAccountType = AccountKind.checking.rawValue
}
