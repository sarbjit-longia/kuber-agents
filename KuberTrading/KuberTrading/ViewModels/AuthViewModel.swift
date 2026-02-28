import Foundation

@Observable
final class AuthViewModel {
    var email = ""
    var password = ""
    var fullName = ""
    var confirmPassword = ""

    var isLoading = false
    var errorMessage: String?
    var showBiometricOption = false

    private let authService = AuthService.shared
    private let biometricService = BiometricService.shared
    private let appState = AppState.shared

    init() {
        Task {
            await checkBiometricAvailability()
            if let savedEmail = await authService.savedEmail() {
                await MainActor.run { email = savedEmail }
            }
        }
    }

    @MainActor
    func login() async {
        guard validateLoginForm() else { return }

        isLoading = true
        errorMessage = nil

        do {
            let user = try await authService.login(email: email, password: password)
            appState.handleLogin(user: user)
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    @MainActor
    func register() async {
        guard validateRegisterForm() else { return }

        isLoading = true
        errorMessage = nil

        do {
            let user = try await authService.register(
                email: email,
                password: password,
                fullName: fullName.isEmpty ? nil : fullName
            )
            appState.handleLogin(user: user)
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    @MainActor
    func loginWithBiometric() async {
        isLoading = true
        errorMessage = nil

        do {
            let authenticated = try await biometricService.authenticate()
            guard authenticated else {
                isLoading = false
                return
            }

            guard let savedEmail = await authService.savedEmail(),
                  let savedToken = try? await KeychainService.shared.read(.accessToken),
                  !savedToken.isEmpty else {
                errorMessage = "No saved credentials. Please log in with email and password."
                isLoading = false
                return
            }

            email = savedEmail
            let user: User = try await APIClient.shared.request(.getCurrentUser)
            appState.handleLogin(user: user)
        } catch {
            errorMessage = "Biometric login failed. Please use email and password."
        }

        isLoading = false
    }

    // MARK: - Validation

    private func validateLoginForm() -> Bool {
        if email.isEmpty {
            errorMessage = "Please enter your email."
            return false
        }
        if password.isEmpty {
            errorMessage = "Please enter your password."
            return false
        }
        if !email.contains("@") {
            errorMessage = "Please enter a valid email address."
            return false
        }
        return true
    }

    private func validateRegisterForm() -> Bool {
        if email.isEmpty {
            errorMessage = "Please enter your email."
            return false
        }
        if !email.contains("@") {
            errorMessage = "Please enter a valid email address."
            return false
        }
        if password.isEmpty {
            errorMessage = "Please enter a password."
            return false
        }
        if password.count < 8 {
            errorMessage = "Password must be at least 8 characters."
            return false
        }
        if password != confirmPassword {
            errorMessage = "Passwords do not match."
            return false
        }
        return true
    }

    private func checkBiometricAvailability() async {
        let biometricType = await biometricService.availableBiometricType()
        let biometricEnabled = await biometricService.isBiometricEnabled()
        let hasToken = await authService.isLoggedIn()

        await MainActor.run {
            showBiometricOption = biometricType != .none && biometricEnabled && hasToken
        }
    }
}
