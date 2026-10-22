import Foundation

/// A money/rate value as the backend sends it: a JSON *string* holding a
/// Python `Decimal` ("2650.00"). Decoding goes straight to `Decimal` so a
/// balance never passes through `Double` and picks up binary rounding noise.
/// A plain JSON number is accepted too, for resilience, but is not expected.
struct APIDecimal: Codable, Hashable, Sendable {
    let value: Decimal

    init(_ value: Decimal) {
        self.value = value
    }

    init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let text = try? container.decode(String.self) {
            guard let parsed = DecimalParsing.parseWire(text) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Not a decimal string: \(text)"
                )
            }
            value = parsed
        } else {
            value = try container.decode(Decimal.self)
        }
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(DecimalParsing.wireString(value))
    }
}

/// Strict conversions between `Decimal` and text. `Decimal(string:)` alone
/// happily parses a prefix ("12abc" -> 12), so every path validates the whole
/// string first.
enum DecimalParsing {
    private static let posix = Locale(identifier: "en_US_POSIX")

    /// Parses the backend's wire format: optional minus, digits, optional
    /// fraction with a dot.
    static func parseWire(_ text: String) -> Decimal? {
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        guard isPlainNumber(trimmed, allowSign: true, maxFractionDigits: nil) else { return nil }
        return Decimal(string: trimmed, locale: posix)
    }

    /// Parses what a person typed into an amount field: accepts both "," and
    /// "." as the decimal separator and ignores spaces used as group
    /// separators. Returns nil for anything that is not a positive amount
    /// with at most `maxFractionDigits` fraction digits.
    static func parseUserAmount(_ text: String, maxFractionDigits: Int = 2) -> Decimal? {
        var cleaned = ""
        for character in text {
            if character == "," {
                cleaned.append(".")
            } else if character == " " || character == "\u{00A0}" || character == "\u{202F}" {
                continue
            } else {
                cleaned.append(character)
            }
        }
        guard isPlainNumber(cleaned, allowSign: false, maxFractionDigits: maxFractionDigits) else { return nil }
        guard let value = Decimal(string: cleaned, locale: posix), value > 0 else { return nil }
        return value
    }

    /// The canonical wire representation ("2650.5"), always with a dot.
    static func wireString(_ value: Decimal) -> String {
        // Decimal's description is locale-independent (always a dot).
        value.description
    }

    private static func isPlainNumber(_ text: String, allowSign: Bool, maxFractionDigits: Int?) -> Bool {
        var body = Substring(text)
        if allowSign, body.first == "-" {
            body = body.dropFirst()
        }
        let parts = body.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 1 || parts.count == 2 else { return false }
        let integerPart = parts[0]
        guard !integerPart.isEmpty, integerPart.count <= 15, integerPart.allSatisfy(\.isASCIIDigit) else { return false }
        if parts.count == 2 {
            let fraction = parts[1]
            guard !fraction.isEmpty, fraction.allSatisfy(\.isASCIIDigit) else { return false }
            if let maxFractionDigits, fraction.count > maxFractionDigits { return false }
        }
        return true
    }
}

private extension Character {
    var isASCIIDigit: Bool {
        guard let ascii = asciiValue else { return false }
        return ascii >= 48 && ascii <= 57
    }
}
