import Foundation
import SwiftData

/// Opens the on-device SwiftData store.
///
/// Where: Application Support/LocalLedger/Ledger.store (+ its -wal/-shm
/// files). Never Documents, so it does not appear in the Files app, and never
/// CloudKit — the data stays on this iPhone. It is still part of the
/// device's iCloud/computer backup when the user has one enabled (see
/// ios/README.md); deleting the app deletes it.
///
/// File protection: `completeUntilFirstUserAuthentication`. The files are
/// encrypted with a key that is unavailable from boot until the first
/// unlock. The stricter `complete` class was rejected on purpose: it evicts
/// the key ~10 s after every lock, and SQLite (under SwiftData) keeps
/// writing its WAL/checkpoints after the app goes to the background — with
/// `complete` those writes fail and can leave the store unusable. The
/// reasoning is spelled out in ios/README.md.
@MainActor
enum LocalStore {
    static let schema = Schema([
        LocalAccount.self,
        LocalCategory.self,
        LocalTransaction.self,
        LocalSettings.self,
    ])

    static let protection = FileProtectionType.completeUntilFirstUserAuthentication

    static func makeContainer() throws -> ModelContainer {
        let directory = try storeDirectory()
        let url = directory.appendingPathComponent("Ledger.store")
        let configuration = ModelConfiguration(
            "LocalLedger",
            schema: schema,
            url: url,
            allowsSave: true,
            cloudKitDatabase: .none
        )
        let container = try ModelContainer(for: schema, configurations: [configuration])
        // Files SQLite created before the directory attribute applied (or
        // left from an earlier version) get the same class explicitly.
        applyProtection(in: directory)
        return container
    }

    /// Creates the directory with the protection class set, so every file
    /// SQLite creates inside inherits it.
    private static func storeDirectory() throws -> URL {
        let fileManager = FileManager.default
        let base = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let directory = base.appendingPathComponent("LocalLedger", isDirectory: true)
        if !fileManager.fileExists(atPath: directory.path) {
            try fileManager.createDirectory(
                at: directory,
                withIntermediateDirectories: true,
                attributes: [FileAttributeKey.protectionKey: protection]
            )
        }
        try? fileManager.setAttributes([FileAttributeKey.protectionKey: protection], ofItemAtPath: directory.path)
        return directory
    }

    private static func applyProtection(in directory: URL) {
        let fileManager = FileManager.default
        guard let names = try? fileManager.contentsOfDirectory(atPath: directory.path) else { return }
        for name in names {
            let path = directory.appendingPathComponent(name).path
            try? fileManager.setAttributes([FileAttributeKey.protectionKey: protection], ofItemAtPath: path)
        }
    }
}
