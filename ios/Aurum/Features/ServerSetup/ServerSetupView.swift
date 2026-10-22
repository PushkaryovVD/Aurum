import SwiftUI

/// Step 1: where is the user's Aurum server? Verified with GET
/// /api/auth/status before it is saved.
struct ServerSetupView: View {
    @Environment(SessionStore.self) private var session
    @State private var model = ServerSetupViewModel()
    @FocusState private var fieldFocused: Bool

    var body: some View {
        @Bindable var model = model
        NavigationStack {
            Form {
                Section {
                    VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                        Image(systemName: "a.circle.fill")
                            .font(.system(size: 44))
                            .foregroundStyle(.tint)
                            .accessibilityHidden(true)
                        Text("server.intro")
                            .font(.body)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, Theme.Spacing.s)
                }

                Section {
                    TextField("server.placeholder", text: $model.address)
                        .keyboardType(.URL)
                        .textContentType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.go)
                        .focused($fieldFocused)
                        .onSubmit { submit() }
                        .accessibilityLabel(Text("server.field"))
                } header: {
                    Text("server.field")
                } footer: {
                    Text("server.footer")
                }

                if let error = model.errorMessage {
                    Section {
                        Label {
                            Text(error)
                        } icon: {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(Theme.negative)
                        }
                        .accessibilityElement(children: .combine)
                    }
                }

                Section {
                    Button(action: submit) {
                        HStack {
                            Spacer()
                            if model.isChecking {
                                ProgressView()
                                    .accessibilityLabel(Text("server.checking"))
                            } else {
                                Text("server.continue").fontWeight(.semibold)
                            }
                            Spacer()
                        }
                        .frame(minHeight: 44)
                    }
                    .disabled(!model.canSubmit)
                }
            }
            .navigationTitle(Text("server.title"))
        }
        .onAppear {
            if model.address.isEmpty, let saved = session.server {
                model.address = saved.displayString
            }
            fieldFocused = true
        }
    }

    private func submit() {
        guard model.canSubmit else { return }
        fieldFocused = false
        Task { await model.submit(using: session) }
    }
}
