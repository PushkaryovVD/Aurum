import Foundation

// Request bodies only the server repository writes. APIClient's encoder
// converts the camelCase coding keys to snake_case.

/// Body of PATCH /api/transactions/{id} (backend TransactionUpdate).
///
/// The server applies only the keys present (`exclude_unset`), so a key left
/// out means "keep the stored value". That is why this type encodes by hand:
/// clearing a category or turning a transfer back into an expense needs an
/// explicit JSON `null`, which synthesized Encodable would silently drop.
/// Tags, splits, merchant and notes are never sent, so they stay untouched.
struct TransactionPatch: Encodable, Sendable {
    let accountId: Int
    let type: String
    let amount: APIDecimal
    /// Always sent: the account currency for a same-currency operation, so a
    /// row that used to be foreign-currency really becomes a plain one.
    let currency: String
    let transactionAmount: APIDecimal
    let categoryId: Int?
    let transferAccountId: Int?
    let transferAmount: APIDecimal?
    let description: String
    /// "YYYY-MM-DD"
    let date: String

    private enum CodingKeys: String, CodingKey {
        case accountId
        case type
        case amount
        case currency
        case transactionAmount
        case categoryId
        case transferAccountId
        case transferAmount
        case description
        case date
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(accountId, forKey: .accountId)
        try container.encode(type, forKey: .type)
        try container.encode(amount, forKey: .amount)
        try container.encode(currency, forKey: .currency)
        try container.encode(transactionAmount, forKey: .transactionAmount)
        // Optional values are encoded with `encode`, not `encodeIfPresent`:
        // nil must reach the server as null.
        try container.encode(categoryId, forKey: .categoryId)
        try container.encode(transferAccountId, forKey: .transferAccountId)
        try container.encode(transferAmount, forKey: .transferAmount)
        try container.encode(description, forKey: .description)
        try container.encode(date, forKey: .date)
    }
}

/// Body of POST /api/accounts (backend AccountCreate).
struct AccountCreateBody: Encodable, Sendable {
    let name: String
    let type: String
    let currency: String
    let color: String?
}

/// Body of PATCH /api/accounts/{id} (backend AccountUpdate). `currency` is
/// sent only when it actually changes (nil is omitted from the JSON); the
/// server refuses a currency change on an account that has operations.
struct AccountPatchBody: Encodable, Sendable {
    let name: String
    let type: String
    let isArchived: Bool
    let currency: String?
}
