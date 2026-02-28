import Foundation

actor UserService {
    static let shared = UserService()

    private init() {}

    // MARK: - Current User

    func getCurrentUser() async throws -> User {
        try await APIClient.shared.request(.getCurrentUser)
    }

    func updateUser(_ update: UserUpdate) async throws -> User {
        try await APIClient.shared.request(.updateCurrentUser(update))
    }

    // MARK: - Subscription

    func getSubscription() async throws -> SubscriptionInfo {
        try await APIClient.shared.request(.getSubscription)
    }

    // MARK: - Telegram

    func getTelegramConfig() async throws -> TelegramConfigResponse {
        try await APIClient.shared.request(.getTelegramConfig)
    }

    func updateTelegramConfig(_ config: TelegramConfig) async throws -> TelegramConfigResponse {
        try await APIClient.shared.request(.updateTelegramConfig(config))
    }

    func testTelegram() async throws {
        try await APIClient.shared.requestVoid(.testTelegram)
    }

    func deleteTelegram() async throws {
        try await APIClient.shared.requestVoid(.deleteTelegram)
    }
}
