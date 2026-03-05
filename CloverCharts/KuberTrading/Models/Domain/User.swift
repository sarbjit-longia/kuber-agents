import Foundation

struct User: Codable, Identifiable {
    let id: String
    let email: String
    let fullName: String?
    let isActive: Bool
    let isSuperuser: Bool
    let subscriptionTier: String
    let maxActivePipelines: Int
    let subscriptionExpiresAt: String?
    let telegramEnabled: Bool
    let telegramChatId: String?
    let createdAt: String
    let updatedAt: String
}

struct UserLogin: Codable {
    let email: String
    let password: String
}

struct UserCreate: Codable {
    let email: String
    let password: String
    var fullName: String?
}

struct TokenResponse: Codable {
    let accessToken: String
    let tokenType: String
}

struct SubscriptionInfo: Codable {
    let tier: String
    let maxActivePipelines: Int
    let currentActivePipelines: Int
    let totalPipelines: Int
    let pipelinesRemaining: Int
    let availableSignals: [String]
    let subscriptionExpiresAt: String?
    let isLimitEnforced: Bool
}

struct UserUpdate: Codable {
    var fullName: String?
    var email: String?
}

struct TelegramConfig: Codable {
    let telegramEnabled: Bool
    let telegramChatId: String?
}

struct TelegramConfigResponse: Codable {
    let telegramEnabled: Bool
    let telegramChatId: String?
    let telegramBotUsername: String?
}
