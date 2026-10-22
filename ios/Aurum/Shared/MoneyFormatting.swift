import Foundation

/// Money is always formatted from `Decimal` with the ISO currency code the
/// backend gave — never converted to Double and never assumed to be KZT.
enum Money {
    static func format(_ value: Decimal, currency: String) -> String {
        value.formatted(.currency(code: currency.uppercased()))
    }

    static func format(_ value: APIDecimal, currency: String) -> String {
        format(value.value, currency: currency)
    }

    /// With an explicit sign: "+12 000 ₸" / "−3 500 ₸". Used for operations,
    /// where direction matters more than magnitude.
    static func signed(_ value: Decimal, currency: String, negative: Bool) -> String {
        let magnitude = format(value < 0 ? -value : value, currency: currency)
        return (negative ? "\u{2212}" : "+") + magnitude
    }

    /// An exchange rate or other plain decimal, shown without currency symbol.
    static func plain(_ value: Decimal) -> String {
        value.formatted(.number.precision(.fractionLength(0...6)))
    }
}
