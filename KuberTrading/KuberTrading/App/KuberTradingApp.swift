import SwiftUI
import SwiftData

@main
struct KuberTradingApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @State private var navigationRouter = NavigationRouter.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(navigationRouter)
                .onOpenURL { url in
                    DeepLinkHandler.shared.handle(url: url)
                }
                .preferredColorScheme(.dark)
        }
        .modelContainer(for: [
            CachedDashboard.self,
            CachedPipeline.self,
            CachedExecution.self,
            CachedScanner.self
        ])
    }
}
