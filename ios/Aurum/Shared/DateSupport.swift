import Foundation

/// A calendar month, as the dashboard and transaction filters use it.
struct MonthRef: Hashable, Sendable, Comparable {
    let year: Int
    let month: Int

    static func current(calendar: Calendar = .current) -> MonthRef {
        let parts = calendar.dateComponents([.year, .month], from: Date())
        return MonthRef(year: parts.year ?? 2000, month: parts.month ?? 1)
    }

    var previous: MonthRef {
        month == 1 ? MonthRef(year: year - 1, month: 12) : MonthRef(year: year, month: month - 1)
    }

    var next: MonthRef {
        month == 12 ? MonthRef(year: year + 1, month: 1) : MonthRef(year: year, month: month + 1)
    }

    var isCurrentOrFuture: Bool { self >= MonthRef.current() }

    /// "October 2026" / "октябрь 2026 г." in the user's locale.
    var title: String {
        var parts = DateComponents()
        parts.year = year
        parts.month = month
        parts.day = 1
        guard let date = Calendar.current.date(from: parts) else { return "\(month)/\(year)" }
        return date.formatted(.dateTime.month(.wide).year())
    }

    static func < (lhs: MonthRef, rhs: MonthRef) -> Bool {
        (lhs.year, lhs.month) < (rhs.year, rhs.month)
    }
}

/// The backend's calendar dates are plain "YYYY-MM-DD" strings with no time
/// zone. They are handled as calendar days, never as instants, so a
/// transaction never drifts to the neighbouring day.
enum APIDate {
    /// "2026-10-22" -> local-calendar Date at the start of that day.
    static func parse(_ text: String) -> Date? {
        let parts = text.split(separator: "-")
        guard parts.count == 3,
              let year = Int(parts[0]), let month = Int(parts[1]), let day = Int(parts[2])
        else { return nil }
        var components = DateComponents()
        components.year = year
        components.month = month
        components.day = day
        return Calendar.current.date(from: components)
    }

    /// Local-calendar Date -> "2026-10-22".
    static func string(from date: Date) -> String {
        let parts = Calendar.current.dateComponents([.year, .month, .day], from: date)
        return pad(parts.year ?? 2000, 4) + "-" + pad(parts.month ?? 1, 2) + "-" + pad(parts.day ?? 1, 2)
    }

    /// For display: "22 Oct 2026" in the user's locale; the raw text if unparsable.
    static func display(_ text: String) -> String {
        guard let date = parse(text) else { return text }
        return date.formatted(date: .abbreviated, time: .omitted)
    }

    /// For list section headers: "Thursday, 22 October".
    static func sectionTitle(_ text: String) -> String {
        guard let date = parse(text) else { return text }
        return date.formatted(.dateTime.weekday(.wide).day().month(.wide).year())
    }

    private static func pad(_ value: Int, _ width: Int) -> String {
        let digits = String(value)
        return digits.count >= width ? digits : String(repeating: "0", count: width - digits.count) + digits
    }
}
