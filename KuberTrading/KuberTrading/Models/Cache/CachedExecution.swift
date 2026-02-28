import Foundation
import SwiftData

@Model
final class CachedExecution {
    @Attribute(.unique) var executionId: String
    var userId: String
    var jsonData: Data
    var status: String
    var cachedAt: Date

    init(executionId: String, userId: String, jsonData: Data, status: String) {
        self.executionId = executionId
        self.userId = userId
        self.jsonData = jsonData
        self.status = status
        self.cachedAt = Date()
    }

    var isCompleted: Bool {
        ["completed", "failed", "cancelled"].contains(status)
    }

    func decode() -> Execution? {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(Execution.self, from: jsonData)
    }
}
