import Foundation

struct ApprovalData: Codable {
    let executionId: String
    let pipelineId: String
    let pipelineName: String
    let symbol: String?
    let mode: String
    let status: String
    let approvalStatus: String?
    let approvalExpiresAt: String?
    let tradeDetails: AnyCodable?
    let preTradeReport: AnyCodable?
}

struct ApprovalAction: Codable {
    let token: String?
}
