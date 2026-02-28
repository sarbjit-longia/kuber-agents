import Foundation
import OSLog

@Observable
final class SettingsViewModel {
    var user: User?
    var subscription: SubscriptionInfo?
    var telegramConfig: TelegramConfigResponse?
    var isLoading = false
    var errorMessage: String?
    var successMessage: String?

    // Profile edit
    var fullName = ""
    var email = ""

    // Telegram
    var telegramChatId = ""
    var telegramEnabled = false

    // Biometric
    var biometricEnabled = false
    var biometricType: BiometricService.BiometricType = .none

    private let logger = Logger(subsystem: "com.kubertrading.app", category: "SettingsVM")

    // MARK: - Load Settings

    @MainActor
    func loadSettings() async {
        isLoading = true
        errorMessage = nil

        do {
            // Load user, subscription, and telegram config in parallel
            async let userResult = UserService.shared.getCurrentUser()
            async let subscriptionResult = UserService.shared.getSubscription()
            async let telegramResult = UserService.shared.getTelegramConfig()

            let (loadedUser, loadedSubscription, loadedTelegram) = try await (
                userResult, subscriptionResult, telegramResult
            )

            user = loadedUser
            subscription = loadedSubscription
            telegramConfig = loadedTelegram

            // Populate form fields
            fullName = loadedUser.fullName ?? ""
            email = loadedUser.email
            telegramChatId = loadedTelegram.telegramChatId ?? ""
            telegramEnabled = loadedTelegram.telegramEnabled

            // Check biometric status
            biometricType = await BiometricService.shared.availableBiometricType()
            biometricEnabled = await BiometricService.shared.isBiometricEnabled()
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to load settings: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to load settings: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Update Profile

    @MainActor
    func updateProfile() async {
        errorMessage = nil
        successMessage = nil

        let trimmedName = fullName.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !trimmedEmail.isEmpty, trimmedEmail.contains("@") else {
            errorMessage = "Please enter a valid email address."
            return
        }

        do {
            let update = UserUpdate(
                fullName: trimmedName.isEmpty ? nil : trimmedName,
                email: trimmedEmail != user?.email ? trimmedEmail : nil
            )

            let updatedUser = try await UserService.shared.updateUser(update)
            user = updatedUser
            fullName = updatedUser.fullName ?? ""
            email = updatedUser.email
            successMessage = "Profile updated successfully."
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to update profile: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Telegram

    @MainActor
    func updateTelegram() async {
        errorMessage = nil
        successMessage = nil

        do {
            let config = TelegramConfig(
                telegramEnabled: telegramEnabled,
                telegramChatId: telegramChatId.isEmpty ? nil : telegramChatId
            )

            let updated = try await UserService.shared.updateTelegramConfig(config)
            telegramConfig = updated
            telegramEnabled = updated.telegramEnabled
            telegramChatId = updated.telegramChatId ?? ""
            successMessage = "Telegram settings updated."
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to update Telegram: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func testTelegram() async {
        errorMessage = nil
        successMessage = nil

        do {
            try await UserService.shared.testTelegram()
            successMessage = "Test message sent to Telegram."
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to test Telegram: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func deleteTelegram() async {
        errorMessage = nil
        successMessage = nil

        do {
            try await UserService.shared.deleteTelegram()
            telegramConfig = nil
            telegramChatId = ""
            telegramEnabled = false
            successMessage = "Telegram configuration removed."
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to delete Telegram: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Biometric

    @MainActor
    func toggleBiometric() async {
        errorMessage = nil
        successMessage = nil

        let newValue = !biometricEnabled

        if newValue {
            // Authenticate before enabling
            do {
                let success = try await BiometricService.shared.authenticate(
                    reason: "Authenticate to enable biometric login"
                )
                guard success else { return }
            } catch {
                errorMessage = error.localizedDescription
                return
            }
        }

        do {
            try await BiometricService.shared.setBiometricEnabled(newValue)
            biometricEnabled = newValue
            successMessage = newValue
                ? "Biometric login enabled."
                : "Biometric login disabled."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Logout

    @MainActor
    func logout() async {
        await AuthService.shared.logout()
        await AppState.shared.handleLogout()
    }
}
