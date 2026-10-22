import SwiftUI

/// Step 2: sign in with the server's own accounts. Uses the system's
/// username/password content types so iCloud Keychain / password managers
/// can fill the form — the app itself never stores the password.
struct LoginView: View {
    @Environment(SessionStore.self) private var session
    @State private var model = LoginViewModel()
    @FocusState private var focusedField: Field?

    private enum Field: Hashable {
        case identifier
        case password
    }

    var body: some View {
        @Bindable var model = model
        NavigationStack {
            Form {
                if session.sessionExpired {
                    Section {
                        Label("login.expired", systemImage: "clock.badge.exclamationmark")
                            .foregroundStyle(.orange)
                    }
                }

                Section {
                    TextField("login.identifier", text: $model.identifier)
                        .textContentType(.username)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.next)
                        .focused($focusedField, equals: .identifier)
                        .onSubmit { focusedField = .password }

                    SecureField("login.password", text: $model.password)
                        .textContentType(.password)
                        .submitLabel(.go)
                        .focused($focusedField, equals: .password)
                        .onSubmit { submit() }
                } footer: {
                    if let server = session.server {
                        Text(L10n.format("login.serverFooter", server.displayString))
                    }
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
                            if model.isSigningIn {
                                ProgressView()
                                    .accessibilityLabel(Text("login.signingIn"))
                            } else {
                                Text("login.submit").fontWeight(.semibold)
                            }
                            Spacer()
                        }
                        .frame(minHeight: 44)
                    }
                    .disabled(!model.canSubmit)
                }

                Section {
                    Button("server.change") {
                        Task { await session.changeServer() }
                    }
                    .disabled(model.isSigningIn)
                }
            }
            .navigationTitle(Text("login.title"))
        }
        .onAppear { focusedField = .identifier }
    }

    private func submit() {
        guard model.canSubmit else { return }
        focusedField = nil
        Task { await model.signIn(using: session) }
    }
}
