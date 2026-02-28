import Foundation
import SwiftUI

@Observable
final class AppState {
    static let shared = AppState()

    var isAuthenticated = false
    var currentUser: User?
    var isLoading = true

    private init() {}

    @MainActor
    func checkAuthState() async {
        isLoading = true
        defer { isLoading = false }

        guard let token = try? await KeychainService.shared.read(.accessToken),
              !token.isEmpty else {
            isAuthenticated = false
            currentUser = nil
            return
        }

        do {
            let user: User = try await APIClient.shared.request(.getCurrentUser)
            currentUser = user
            isAuthenticated = true
        } catch {
            isAuthenticated = false
            currentUser = nil
            try? await KeychainService.shared.deleteAll()
        }
    }

    @MainActor
    func handleLogin(user: User) {
        currentUser = user
        isAuthenticated = true
    }

    @MainActor
    func handleLogout() async {
        try? await KeychainService.shared.deleteAll()
        currentUser = nil
        isAuthenticated = false
    }
}
