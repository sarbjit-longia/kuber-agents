import Foundation

actor AuthService {
    static let shared = AuthService()

    private init() {}

    func login(email: String, password: String) async throws -> User {
        let credentials = UserLogin(email: email, password: password)
        let tokenResponse: TokenResponse = try await APIClient.shared.request(.login(credentials))

        try await KeychainService.shared.save(tokenResponse.accessToken, for: .accessToken)
        try await KeychainService.shared.save(email, for: .userEmail)

        let user: User = try await APIClient.shared.request(.getCurrentUser)
        return user
    }

    func register(email: String, password: String, fullName: String?) async throws -> User {
        let userData = UserCreate(email: email, password: password, fullName: fullName)
        let _: User = try await APIClient.shared.request(.register(userData))

        // Auto-login after registration
        return try await login(email: email, password: password)
    }

    func logout() async {
        try? await KeychainService.shared.deleteAll()
    }

    func isLoggedIn() async -> Bool {
        guard let token = try? await KeychainService.shared.read(.accessToken) else {
            return false
        }
        return !token.isEmpty
    }

    func savedEmail() async -> String? {
        try? await KeychainService.shared.read(.userEmail)
    }
}
