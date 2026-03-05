import Foundation

struct ToolMetadata: Codable, Identifiable {
    var id: String { toolType }
    let toolType: String
    let name: String
    let description: String
    let category: String
    let configSchema: AnyCodable?
    let isBroker: Bool?
}

struct ToolInstance: Codable {
    let toolType: String
    var enabled: Bool
    var config: [String: AnyCodable]
    var metadata: ToolMetadata?
}

struct AvailableToolsResponse: Codable {
    let tools: [ToolMetadata]
}
