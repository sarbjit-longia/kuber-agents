import Foundation

struct Scanner: Codable, Identifiable {
    let id: String
    let userId: String
    let name: String
    let description: String?
    let scannerType: String
    var config: [String: AnyCodable]
    var isActive: Bool
    let refreshInterval: Int?
    let lastRefreshedAt: String?
    let createdAt: String
    let updatedAt: String
    let tickerCount: Int?
    let pipelineCount: Int?
}

struct ScannerCreate: Codable {
    let name: String
    let description: String?
    let scannerType: String
    let config: [String: AnyCodable]
    let isActive: Bool?
    let refreshInterval: Int?
}

struct ScannerUpdate: Codable {
    var name: String?
    var description: String?
    var config: [String: AnyCodable]?
    var isActive: Bool?
    var refreshInterval: Int?
}

struct ScannerTickersResponse: Codable {
    let tickers: [String]
    let total: Int
}

struct ScannerUsageResponse: Codable {
    let pipelineCount: Int
    let pipelines: [ScannerUsagePipeline]
}

struct ScannerUsagePipeline: Codable, Identifiable {
    let id: String
    let name: String
}

struct SignalType: Codable, Identifiable {
    var id: String { signalType }
    let signalType: String
    let name: String
    let description: String
    let generator: String
    let isFree: Bool
    let typicalFrequency: String
    let requiresConfidenceFilter: Bool
    let defaultConfidence: Double?
    let icon: String
    let category: String
}
