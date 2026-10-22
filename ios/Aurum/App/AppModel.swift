import Foundation
import Observation

/// Where this iPhone keeps the user's finances. The two modes are
/// independent ledgers: they never sync, and switching between them never
/// deletes the other one's data. Moving data across is done with a backup.
enum StorageMode: String, Sendable, CaseIterable, Identifiable {
    /// "My server": the user's self-hosted Aurum (Postgres) over its API.
    case server
    /// "Only on iPhone": a SwiftData store on the device, fully offline.
    case local

    var id: String { rawValue }

    private static let defaultsKey = "aurum.storageMode"

    /// The saved choice. An install that already has a server address from
    /// before modes existed keeps working in server mode without asking.
    static func loadSaved() -> StorageMode? {
        if let raw = UserDefaults.standard.string(forKey: defaultsKey), let mode = StorageMode(rawValue: raw) {
            return mode
        }
        return ServerAddress.loadSaved() != nil ? .server : nil
    }

    func save() {
        UserDefaults.standard.set(rawValue, forKey: Self.defaultsKey)
    }
}

/// App-wide state above the two modes: which mode is active, the server
/// session (server mode) and the opened device store (local mode).
@MainActor
@Observable
final class AppModel {
    enum LocalState {
        case closed
        case ready(LocalRepository)
        case failed(String)
    }

    /// nil until the user picked a mode (first launch).
    private(set) var mode: StorageMode?
    let session: SessionStore
    private(set) var local: LocalState = .closed

    init() {
        session = SessionStore()
        mode = StorageMode.loadSaved()
        if mode == .local {
            openLocalStore()
        }
    }

    func choose(_ newMode: StorageMode) {
        newMode.save()
        mode = newMode
        if newMode == .local {
            openLocalStore()
        }
        // Switching to server mode does not touch the device store and vice
        // versa: the other mode's data simply stays where it is.
    }

    /// Opens (creating on first use) the device store. Safe to call again
    /// after a failure.
    func openLocalStore() {
        if case .ready = local { return }
        do {
            let container = try LocalStore.makeContainer()
            local = .ready(try LocalRepository(container: container))
        } catch {
            local = .failed(error.displayMessage)
        }
    }

    var localRepository: LocalRepository? {
        if case .ready(let repository) = local { return repository }
        return nil
    }
}
