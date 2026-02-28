import Foundation
import SwiftData

@Model
final class CachedPipeline {
    @Attribute(.unique) var pipelineId: String
    var userId: String
    var jsonData: Data
    var cachedAt: Date
    var staleAfterMinutes: Int = 30

    init(pipelineId: String, userId: String, jsonData: Data) {
        self.pipelineId = pipelineId
        self.userId = userId
        self.jsonData = jsonData
        self.cachedAt = Date()
    }

    var isStale: Bool {
        Date().timeIntervalSince(cachedAt) > Double(staleAfterMinutes * 60)
    }

    func decode() -> Pipeline? {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(Pipeline.self, from: jsonData)
    }
}
