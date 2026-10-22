import SwiftUI
import UniformTypeIdentifiers

/// "More → Backup" in device mode: export the ledger to a JSON file (to
/// Files, iCloud Drive, AirDrop…) and import one back, replacing everything
/// after an explicit confirmation.
struct BackupView: View {
    @State private var model: BackupViewModel
    @State private var isExporting = false
    @State private var isImporting = false
    @State private var confirmImport = false

    init(repository: LocalRepository) {
        _model = State(initialValue: BackupViewModel(repository: repository))
    }

    var body: some View {
        // fileExporter and fileImporter sit on different views on purpose:
        // attached to the same one, SwiftUI presents only one of them.
        VStack(spacing: 0) {
            list
                .fileExporter(
                    isPresented: $isExporting,
                    document: model.exportDocument,
                    contentType: .json,
                    defaultFilename: model.exportFilename
                ) { result in
                    model.exportFinished(result)
                }
        }
        .fileImporter(isPresented: $isImporting, allowedContentTypes: [.json]) { result in
            model.fileSelected(result)
            confirmImport = model.pendingImport != nil
        }
        .alert(
            Text("backup.import.confirmTitle"),
            isPresented: $confirmImport,
            presenting: model.pendingImport
        ) { _ in
            Button("backup.import.replace", role: .destructive) {
                model.confirmImport()
            }
            Button("action.cancel", role: .cancel) {
                model.cancelImport()
            }
        } message: { plan in
            Text(BackupViewModel.summary(of: plan))
        }
        .navigationTitle(Text("backup.title"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private var list: some View {
        List {
            Section {
                Text("backup.about")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Section {
                Button {
                    if model.prepareExport() {
                        isExporting = true
                    }
                } label: {
                    Label("backup.export", systemImage: "square.and.arrow.up")
                }
                .disabled(model.isWorking)
            } footer: {
                Text("backup.export.footer")
            }

            Section {
                Button {
                    isImporting = true
                } label: {
                    Label("backup.import", systemImage: "square.and.arrow.down")
                }
                .disabled(model.isWorking)
            } footer: {
                Text("backup.import.footer")
            }

            if let message = model.message {
                Section {
                    Label {
                        Text(message.text)
                    } icon: {
                        Image(systemName: message.isError ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                            .foregroundStyle(message.isError ? Theme.negative : Theme.income)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
        .listStyle(.insetGrouped)
    }
}
