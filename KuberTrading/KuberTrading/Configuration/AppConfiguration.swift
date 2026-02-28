import Foundation

enum AppEnvironment: String {
    case development
    case staging
    case production
}

@Observable
final class AppConfiguration {
    static let shared = AppConfiguration()

    let environment: AppEnvironment
    let baseURL: URL
    let wsBaseURL: URL

    private init() {
        #if DEBUG
        self.environment = .development
        self.baseURL = URL(string: "http://localhost:8000")!
        self.wsBaseURL = URL(string: "ws://localhost:8000")!
        #else
        self.environment = .production
        self.baseURL = URL(string: "https://api.kubertrading.com")!
        self.wsBaseURL = URL(string: "wss://api.kubertrading.com")!
        #endif
    }

    var apiBaseURL: URL {
        baseURL.appendingPathComponent("api/v1")
    }

    var wsURL: URL {
        wsBaseURL.appendingPathComponent("api/v1/ws/executions")
    }
}
