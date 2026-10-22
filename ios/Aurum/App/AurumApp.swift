import SwiftUI

@main
struct AurumApp: App {
    @State private var app = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(app)
                // Server-mode screens keep reading the session directly.
                .environment(app.session)
        }
    }
}
