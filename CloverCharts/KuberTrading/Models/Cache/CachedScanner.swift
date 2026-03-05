import Foundation
import SwiftData

@Model
final class CachedScanner {
    @Attribute(.unique) var scannerId: String
    var userId: String
    var jsonData: Data
    var cachedAt: Date
    var staleAfterMinutes: Int = 30

    init(scannerId: String, userId: String, jsonData: Data) {
        self.scannerId = scannerId
        self.userId = userId
        self.jsonData = jsonData
        self.cachedAt = Date()
    }

    var isStale: Bool {
        Date().timeIntervalSince(cachedAt) > Double(staleAfterMinutes * 60)
    }

    func decode() -> Scanner? {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(Scanner.self, from: jsonData)
    }
}
