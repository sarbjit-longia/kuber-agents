import LocalAuthentication

actor BiometricService {
    static let shared = BiometricService()

    private init() {}

    enum BiometricType {
        case none
        case faceID
        case touchID
    }

    func availableBiometricType() -> BiometricType {
        let context = LAContext()
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else {
            return .none
        }
        switch context.biometryType {
        case .faceID: return .faceID
        case .touchID: return .touchID
        default: return .none
        }
    }

    func authenticate(reason: String = "Authenticate to access KuberTrading") async throws -> Bool {
        let context = LAContext()
        context.localizedCancelTitle = "Use Password"

        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else {
            throw BiometricError.notAvailable
        }

        do {
            let success = try await context.evaluatePolicy(
                .deviceOwnerAuthenticationWithBiometrics,
                localizedReason: reason
            )
            return success
        } catch let authError as LAError {
            switch authError.code {
            case .userCancel, .userFallback, .systemCancel:
                return false
            case .biometryNotAvailable:
                throw BiometricError.notAvailable
            case .biometryNotEnrolled:
                throw BiometricError.notEnrolled
            case .biometryLockout:
                throw BiometricError.lockedOut
            default:
                throw BiometricError.failed(authError.localizedDescription)
            }
        }
    }

    func isBiometricEnabled() async -> Bool {
        guard let value = try? await KeychainService.shared.read(.biometricEnabled) else {
            return false
        }
        return value == "true"
    }

    func setBiometricEnabled(_ enabled: Bool) async throws {
        try await KeychainService.shared.save(enabled ? "true" : "false", for: .biometricEnabled)
    }
}

enum BiometricError: LocalizedError {
    case notAvailable
    case notEnrolled
    case lockedOut
    case failed(String)

    var errorDescription: String? {
        switch self {
        case .notAvailable:
            return "Biometric authentication is not available on this device."
        case .notEnrolled:
            return "No biometric data enrolled. Please set up Face ID or Touch ID in Settings."
        case .lockedOut:
            return "Biometric authentication is locked. Please use your passcode."
        case .failed(let message):
            return "Authentication failed: \(message)"
        }
    }
}
