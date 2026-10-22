import Foundation

/// The honest state of something loaded from the server.
///
/// `value` and `error` are independent on purpose: after a failed refresh the
/// last good value stays visible *and* the failure is reported, so stale data
/// is labelled as such and an error never masquerades as "zero" or "empty".
struct RemoteContent<Value> {
    private(set) var value: Value?
    private(set) var error: String?
    private(set) var isLoading = false
    private(set) var updatedAt: Date?

    init() {}

    var hasValue: Bool { value != nil }

    /// Showing a previous value while the latest refresh failed.
    var isStale: Bool { value != nil && error != nil }

    mutating func beginLoading() {
        isLoading = true
    }

    mutating func succeed(_ newValue: Value) {
        value = newValue
        error = nil
        isLoading = false
        updatedAt = Date()
    }

    mutating func fail(_ message: String) {
        error = message
        isLoading = false
    }

    /// A cancelled load is neither a success nor a failure.
    mutating func cancel() {
        isLoading = false
    }

    mutating func reset() {
        self = RemoteContent()
    }
}

extension RemoteContent: Sendable where Value: Sendable {}
