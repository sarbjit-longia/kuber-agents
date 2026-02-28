import Foundation

struct DeviceRegistration: Codable {
    let deviceToken: String
    let platform: String
}

struct DeviceRegistrationResponse: Codable {
    let id: String
    let deviceToken: String
    let platform: String
    let isActive: Bool
}
