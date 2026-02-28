import Foundation

struct AgentMetadata: Codable, Identifiable {
    var id: String { agentType }
    let agentType: String
    let name: String
    let description: String
    let category: String
    let version: String
    let icon: String?
    let pricingRate: Double
    let isFree: Bool
    let requiresTimeframes: [String]?
    let requiresMarketData: Bool?
    let requiresPosition: Bool?
    let configSchema: AgentConfigSchema
}

struct AgentConfigSchema: Codable {
    let type: String
    let title: String
    let description: String?
    let properties: [String: AnyCodable]
    let required: [String]?
}

struct ValidateInstructionsRequest: Codable {
    let agentType: String
    let instructions: String
    let documentUrl: String?
}

struct ValidateInstructionsResponse: Codable {
    let isValid: Bool
    let errors: [String]?
    let detectedTools: [DetectedTool]?
    let estimatedToolCost: Double?
    let estimatedLlmCost: Double?
}

struct DetectedTool: Codable {
    let toolType: String
    let name: String
}
