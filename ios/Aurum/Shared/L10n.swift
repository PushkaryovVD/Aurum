import Foundation

/// Lookup for strings built in code (errors, formatted labels). Static UI
/// text uses `Text("key")`, which resolves the same Localizable.strings
/// tables (en.lproj / ru.lproj) through LocalizedStringKey.
enum L10n {
    static func text(_ key: String) -> String {
        NSLocalizedString(key, comment: "")
    }

    /// For keys built from server values (e.g. an account type the app does
    /// not know yet): shows the raw value instead of the bare key.
    static func text(_ key: String, fallback: String) -> String {
        let value = NSLocalizedString(key, comment: "")
        return value == key ? fallback : value
    }

    /// Format strings in the tables use only `%@` placeholders, so every
    /// argument is passed as a string — no Int/CVarArg width surprises.
    static func format(_ key: String, _ arguments: String...) -> String {
        let format = NSLocalizedString(key, comment: "")
        let cArguments: [any CVarArg] = arguments.map { NSString(string: $0) }
        return String(format: format, arguments: cArguments)
    }
}
