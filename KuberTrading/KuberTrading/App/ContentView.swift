import SwiftUI

struct ContentView: View {
    @State private var appState = AppState.shared

    var body: some View {
        Group {
            if appState.isLoading {
                ProgressView("Loading...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color(.systemBackground))
            } else if appState.isAuthenticated {
                TabBarView()
            } else {
                LoginView()
            }
        }
        .task {
            await appState.checkAuthState()
        }
    }
}

#Preview {
    ContentView()
}
