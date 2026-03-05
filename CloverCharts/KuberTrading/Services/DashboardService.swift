import Foundation

actor DashboardService {
    static let shared = DashboardService()

    private init() {}

    func loadDashboard() async throws -> DashboardData {
        let timezone = TimeZone.current.identifier
        return try await APIClient.shared.request(.getDashboard(timezone: timezone))
    }
}
