import Foundation

struct WebSocketMessage: Codable {
    let type: String
    let executionId: String?
    let data: AnyCodable?
    let message: String?
    let timestamp: String?
}

struct WebSocketCommand: Codable {
    let action: String
    let executionId: String?

    enum CodingKeys: String, CodingKey {
        case action
        case executionId = "execution_id"
    }
}
