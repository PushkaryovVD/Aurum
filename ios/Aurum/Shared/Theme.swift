import SwiftUI
import UIKit

/// Design tokens for the native client. Colors come from the system's
/// semantic palette (automatic light/dark + increased-contrast variants);
/// only the brand accent lives in the asset catalog (AccentColor).
enum Theme {
    enum Spacing {
        static let xs: CGFloat = 4
        static let s: CGFloat = 8
        static let m: CGFloat = 12
        static let l: CGFloat = 16
        static let xl: CGFloat = 24
    }

    enum Radius {
        static let card: CGFloat = 14
        static let control: CGFloat = 10
    }

    /// Income/negative hues tuned for WCAG AA text contrast (>= 4.5:1) on
    /// both the light and the dark grouped backgrounds — the stock system
    /// green is too light to read as text on white.
    static var income: Color {
        adaptive(light: (0.0, 0.43, 0.16), dark: (0.42, 0.86, 0.52))
    }
    static var expense: Color { .primary }
    static var negative: Color {
        adaptive(light: (0.70, 0.15, 0.12), dark: (1.0, 0.45, 0.42))
    }
    static var cardBackground: Color { Color(uiColor: .secondarySystemGroupedBackground) }
    static var groupedBackground: Color { Color(uiColor: .systemGroupedBackground) }

    private static func adaptive(
        light: (Double, Double, Double),
        dark: (Double, Double, Double)
    ) -> Color {
        // Only plain Double tuples are captured, so the provider closure stays
        // Sendable-clean whatever the SDK's annotation on it is.
        Color(uiColor: UIColor { traits in
            let rgb = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: rgb.0, green: rgb.1, blue: rgb.2, alpha: 1)
        })
    }
}

extension Color {
    /// Parses the backend's "#RRGGBB" category/account colors; nil if malformed.
    init?(hex: String?) {
        guard var text = hex?.trimmingCharacters(in: .whitespaces) else { return nil }
        if text.hasPrefix("#") {
            text.removeFirst()
        }
        guard text.count == 6, let rgb = UInt32(text, radix: 16) else { return nil }
        self.init(
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255
        )
    }
}
