import SwiftUI

/// Where the finances live: the user's own server or only this iPhone.
/// Shown full-screen on first launch and as a sheet from "More". Each option
/// says plainly where the data is stored and what can make it disappear.
struct ModeSelectionView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss

    /// First launch: picking a mode applies it at once. From "More": the
    /// switch is confirmed first and the sheet closes afterwards.
    let isOnboarding: Bool

    @State private var pendingMode: StorageMode?
    @State private var confirmSwitch = false

    init(isOnboarding: Bool) {
        self.isOnboarding = isOnboarding
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                    if isOnboarding {
                        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                            Image(systemName: "a.circle.fill")
                                .font(.system(size: 44))
                                .foregroundStyle(.tint)
                                .accessibilityHidden(true)
                            Text("mode.intro")
                                .font(.body)
                                .foregroundStyle(.secondary)
                        }
                    }

                    ModeCard(
                        mode: .local,
                        systemImage: "iphone",
                        title: "mode.local.title",
                        summary: "mode.local.summary",
                        points: ["mode.local.point.offline", "mode.local.point.backup", "mode.local.point.delete"],
                        isCurrent: !isOnboarding && app.mode == .local
                    ) { select(.local) }

                    ModeCard(
                        mode: .server,
                        systemImage: "server.rack",
                        title: "mode.server.title",
                        summary: "mode.server.summary",
                        points: ["mode.server.point.where", "mode.server.point.https", "mode.server.point.web"],
                        isCurrent: !isOnboarding && app.mode == .server
                    ) { select(.server) }

                    Text("mode.footer")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, Theme.Spacing.l)
                .padding(.vertical, Theme.Spacing.m)
                .frame(maxWidth: 640, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .background(Theme.groupedBackground)
            .navigationTitle(Text("mode.title"))
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    if !isOnboarding {
                        Button("action.cancel") { dismiss() }
                    }
                }
            }
            .confirmationDialog(
                Text("mode.switch.confirm"),
                isPresented: $confirmSwitch,
                titleVisibility: .visible,
                presenting: pendingMode
            ) { mode in
                Button(mode == .local ? LocalizedStringKey("mode.switch.toLocal") : LocalizedStringKey("mode.switch.toServer")) {
                    app.choose(mode)
                    dismiss()
                }
                Button("action.cancel", role: .cancel) {}
            } message: { _ in
                Text("mode.switch.message")
            }
        }
    }

    private func select(_ mode: StorageMode) {
        if isOnboarding {
            app.choose(mode)
        } else if mode == app.mode {
            dismiss()
        } else {
            pendingMode = mode
            confirmSwitch = true
        }
    }
}

/// One selectable option: a large tappable card with the facts that matter
/// for the choice.
private struct ModeCard: View {
    let mode: StorageMode
    let systemImage: String
    let title: LocalizedStringKey
    let summary: LocalizedStringKey
    let points: [LocalizedStringKey]
    let isCurrent: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s) {
                    Image(systemName: systemImage)
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(.tint)
                        .accessibilityHidden(true)
                    Text(title)
                        .font(.headline)
                        .foregroundStyle(.primary)
                    Spacer(minLength: Theme.Spacing.s)
                    if isCurrent {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(.tint)
                            .accessibilityLabel(Text("mode.current"))
                    } else {
                        Image(systemName: "chevron.right")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(.tertiary)
                            .accessibilityHidden(true)
                    }
                }
                Text(summary)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    ForEach(Array(points.enumerated()), id: \.offset) { _, point in
                        Label {
                            Text(point)
                                .fixedSize(horizontal: false, vertical: true)
                        } icon: {
                            Image(systemName: "circle.fill")
                                .font(.system(size: 5))
                                .foregroundStyle(.secondary)
                        }
                        .font(.footnote)
                        .foregroundStyle(.primary)
                    }
                }
            }
            .multilineTextAlignment(.leading)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(Theme.Spacing.l)
            .background(Theme.cardBackground, in: RoundedRectangle(cornerRadius: Theme.Radius.card))
            .overlay {
                RoundedRectangle(cornerRadius: Theme.Radius.card)
                    .strokeBorder(isCurrent ? Color.accentColor : Color.clear, lineWidth: 2)
            }
            .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.card))
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(isCurrent ? [.isButton, .isSelected] : .isButton)
    }
}
