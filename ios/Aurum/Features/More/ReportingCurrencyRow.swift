import SwiftUI

/// The device ledger's reporting currency (the server's app_settings
/// currency): what the Overview totals are shown in. Saved on submit.
struct ReportingCurrencyRow: View {
    let repository: LocalRepository

    @State private var code = ""
    @State private var errorText: String?
    @FocusState private var isFocused: Bool

    init(repository: LocalRepository) {
        self.repository = repository
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            LabeledContent {
                TextField("add.currencyCode", text: $code)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                    .multilineTextAlignment(.trailing)
                    .font(.body.monospaced())
                    .submitLabel(.done)
                    .focused($isFocused)
                    .onSubmit { save() }
                    .onChange(of: code) {
                        let cleaned = String(code.uppercased().prefix(3))
                        if cleaned != code {
                            code = cleaned
                        }
                    }
                    .onChange(of: isFocused) {
                        if !isFocused { save() }
                    }
                    .accessibilityLabel(Text("more.reportingCurrency"))
            } label: {
                Text("more.reportingCurrency")
            }
            if let errorText {
                Text(errorText)
                    .font(.footnote)
                    .foregroundStyle(Theme.negative)
            }
        }
        .onAppear {
            code = repository.reportingCurrency
        }
    }

    private func save() {
        guard code != repository.reportingCurrency else {
            errorText = nil
            return
        }
        do {
            try repository.setReportingCurrency(code)
            errorText = nil
        } catch {
            errorText = error.displayMessage
        }
    }
}
