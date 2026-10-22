import Foundation
import Observation
import SwiftUI
import UniformTypeIdentifiers

/// Export of the device ledger to a JSON backup and import of one (from this
/// app or from the server's Settings → Backup & Restore). An import never
/// touches the store until the user confirmed the summary of what the file
/// contains.
@MainActor
@Observable
final class BackupViewModel {
    private(set) var exportDocument: BackupDocument?
    private(set) var exportFilename = "aurum-backup"
    /// A file was read and checked; waiting for the user's confirmation.
    private(set) var pendingImport: BackupCodec.ImportPlan?
    private(set) var message: Message?
    private(set) var isWorking = false

    struct Message: Equatable {
        let text: String
        let isError: Bool
    }

    private let repository: LocalRepository

    init(repository: LocalRepository) {
        self.repository = repository
    }

    // MARK: - Export

    /// Prepares the document; returns true when the exporter can be shown.
    func prepareExport() -> Bool {
        message = nil
        do {
            let now = Date()
            let today = APIDate.string(from: now)
            let data = try BackupCodec.encode(
                try repository.snapshot(),
                exportedAt: now,
                appVersion: "ios-" + Self.appVersion,
                today: today
            )
            exportDocument = BackupDocument(data: data)
            exportFilename = "aurum-backup-" + today
            return true
        } catch {
            message = Message(text: error.displayMessage, isError: true)
            return false
        }
    }

    func exportFinished(_ result: Result<URL, any Error>) {
        exportDocument = nil
        switch result {
        case .success:
            message = Message(text: L10n.text("backup.export.done"), isError: false)
        case .failure(let error):
            if !error.isCancellation {
                message = Message(text: error.displayMessage, isError: true)
            }
        }
    }

    // MARK: - Import

    /// Reads and checks the picked file. Nothing is stored yet.
    func fileSelected(_ result: Result<URL, any Error>) {
        message = nil
        pendingImport = nil
        let url: URL
        switch result {
        case .success(let picked):
            url = picked
        case .failure(let error):
            if !error.isCancellation {
                message = Message(text: error.displayMessage, isError: true)
            }
            return
        }
        // Files outside the app's sandbox (iCloud Drive, On My iPhone) are
        // only readable inside a security-scoped access window.
        let scoped = url.startAccessingSecurityScopedResource()
        defer {
            if scoped { url.stopAccessingSecurityScopedResource() }
        }
        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            message = Message(text: L10n.text("backup.error.unreadable"), isError: true)
            return
        }
        switch BackupCodec.decode(data, fallbackCurrency: repository.reportingCurrency) {
        case .success(let plan):
            pendingImport = plan
        case .failure(let error):
            message = Message(text: error.localizedDescription, isError: true)
        }
    }

    func cancelImport() {
        pendingImport = nil
    }

    /// Replaces the device ledger with the confirmed backup.
    func confirmImport() {
        guard let plan = pendingImport else { return }
        pendingImport = nil
        isWorking = true
        defer { isWorking = false }
        do {
            try repository.replaceAll(with: plan.snapshot)
            message = Message(
                text: L10n.format(
                    "backup.import.done",
                    String(plan.snapshot.accounts.count),
                    String(plan.snapshot.entries.count)
                ),
                isError: false
            )
        } catch {
            message = Message(text: error.displayMessage, isError: true)
        }
    }

    /// The confirmation text: what the file holds and what will be lost.
    static func summary(of plan: BackupCodec.ImportPlan) -> String {
        var lines = [
            L10n.format(
                "backup.import.counts",
                String(plan.snapshot.accounts.count),
                String(plan.snapshot.categories.count),
                String(plan.snapshot.entries.count)
            ),
        ]
        if let exportedAt = plan.exportedAt, !exportedAt.isEmpty {
            lines.append(L10n.format("backup.import.exportedAt", exportedAt))
        }
        if plan.mergedSplits > 0 {
            lines.append(L10n.format("backup.import.splitsMerged", String(plan.mergedSplits)))
        }
        if plan.uncategorizedSplits > 0 {
            lines.append(L10n.format("backup.import.splitsUncategorized", String(plan.uncategorizedSplits)))
        }
        if plan.operationsWithTags > 0 {
            lines.append(L10n.format("backup.import.tags", String(plan.operationsWithTags)))
        }
        if plan.ignoredRecords > 0 {
            lines.append(L10n.format("backup.import.ignored", String(plan.ignoredRecords)))
        }
        lines.append(L10n.text("backup.import.replaceWarning"))
        return lines.joined(separator: "\n\n")
    }

    private static var appVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0"
    }
}

/// The exported JSON as a document for `fileExporter`.
struct BackupDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.json] }

    let data: Data

    init(data: Data) {
        self.data = data
    }

    init(configuration: ReadConfiguration) throws {
        guard let contents = configuration.file.regularFileContents else {
            throw CocoaError(.fileReadCorruptFile)
        }
        data = contents
    }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        FileWrapper(regularFileWithContents: data)
    }
}
