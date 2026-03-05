import UIKit
import UserNotifications

@Observable
final class PushNotificationService {
    static let shared = PushNotificationService()

    var isAuthorized = false
    var deviceToken: String?

    private init() {}

    func requestPermission() async -> Bool {
        do {
            let granted = try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .badge, .sound])
            await MainActor.run {
                isAuthorized = granted
                if granted {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
            return granted
        } catch {
            print("Push notification permission error: \(error)")
            return false
        }
    }

    func checkPermissionStatus() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        await MainActor.run {
            isAuthorized = settings.authorizationStatus == .authorized
        }
    }

    func handleDeviceToken(_ token: String) async {
        deviceToken = token
        guard AppState.shared.isAuthenticated else { return }

        do {
            let registration = DeviceRegistration(deviceToken: token, platform: "ios")
            let _: DeviceRegistrationResponse = try await APIClient.shared.request(.registerDevice(registration))
        } catch {
            print("Failed to register device token: \(error)")
        }
    }

    func unregisterDevice(deviceId: String) async throws {
        try await APIClient.shared.requestVoid(.unregisterDevice(deviceId: deviceId))
    }
}
