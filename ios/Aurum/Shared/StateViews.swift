import SwiftUI

/// Full-screen "loading for the first time" state.
struct LoadingStateView: View {
    var body: some View {
        ProgressView {
            Text("state.loading")
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .combine)
    }
}

/// Full-screen failure with nothing to show yet. Clearly an error — never
/// rendered as an empty list or as zeros.
struct ErrorStateView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("state.error.title", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button(action: retry) {
                Text("action.retry")
                    .frame(minWidth: 120)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
    }
}

/// The request succeeded and there is genuinely nothing.
struct EmptyStateView: View {
    let title: LocalizedStringKey
    let systemImage: String
    var message: LocalizedStringKey?

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: systemImage)
        } description: {
            if let message {
                Text(message)
            }
        }
    }
}

/// Banner over content that could not be refreshed: the numbers below are
/// from an earlier successful load, and the user is told so.
struct StaleDataBanner: View {
    let message: String
    let updatedAt: Date?
    let retry: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: Theme.Spacing.m) {
            Image(systemName: "exclamationmark.arrow.triangle.2.circlepath")
                .foregroundStyle(.orange)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                Text("state.stale.title")
                    .font(.subheadline.weight(.semibold))
                if let updatedAt {
                    Text(L10n.format("state.stale.updatedAt", updatedAt.formatted(date: .omitted, time: .shortened)))
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Text(message)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            Button(action: retry) {
                Text("action.retry")
            }
            .buttonStyle(.bordered)
        }
        .padding(Theme.Spacing.m)
        .background(Color.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: Theme.Radius.control))
        .accessibilityElement(children: .contain)
    }
}

/// Picks the right state for a `RemoteContent`: first-load spinner, error
/// with retry, or the content (with a stale banner when a refresh failed).
struct RemoteContentView<Value, Content: View>: View {
    let content: RemoteContent<Value>
    let retry: () -> Void
    @ViewBuilder let loaded: (Value) -> Content

    var body: some View {
        if let value = content.value {
            loaded(value)
        } else if let error = content.error {
            ErrorStateView(message: error, retry: retry)
        } else {
            LoadingStateView()
        }
    }
}
