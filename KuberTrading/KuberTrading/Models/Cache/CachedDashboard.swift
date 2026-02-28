import Foundation
import SwiftData

@Model
final class CachedDashboard {
    var userId: String
    var jsonData: Data
    var cachedAt: Date
    var staleAfterMinutes: Int = 5

    init(userId: String, jsonData: Data) {
        self.userId = userId
        self.jsonData = jsonData
        self.cachedAt = Date()
    }

    var isStale: Bool {
        Date().timeIntervalSince(cachedAt) > Double(staleAfterMinutes * 60)
    }

    func decode() -> DashboardData? {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(DashboardData.self, from: jsonData)
    }
}
