import Foundation

struct Pipeline: Codable, Identifiable {
    let id: String
    let userId: String
    let name: String
    let description: String?
    var config: PipelineConfig
    var isActive: Bool
    var triggerMode: String
    var scannerId: String?
    var signalSubscriptions: [SignalSubscription]?
    var scannerTickers: [String]?
    var notificationEnabled: Bool
    var notificationEvents: [String]?
    var requireApproval: Bool
    var approvalModes: [String]?
    var approvalTimeoutMinutes: Int
    var approvalChannels: [String]?
    var approvalPhone: String?
    let createdAt: String
    let updatedAt: String
}

struct PipelineConfig: Codable {
    var symbol: String?
    var mode: String?
    var brokerTool: AnyCodable?
    var nodes: [PipelineNode]
    var edges: [PipelineEdge]
}

struct PipelineNode: Codable, Identifiable {
    let id: String
    let agentType: String
    var config: [String: AnyCodable]
    var position: NodePosition?
}

struct NodePosition: Codable {
    let x: Double
    let y: Double
}

struct PipelineEdge: Codable {
    let from: String
    let to: String
}

struct PipelineCreate: Codable {
    let name: String
    let description: String?
    let config: PipelineConfig
    let isActive: Bool
    let triggerMode: String
    let scannerId: String?
    let signalSubscriptions: [SignalSubscription]?
    let notificationEnabled: Bool
    let notificationEvents: [String]?
    let requireApproval: Bool
    let approvalModes: [String]?
    let approvalTimeoutMinutes: Int
    let approvalChannels: [String]?
    let approvalPhone: String?
}

struct PipelineUpdate: Codable {
    var name: String?
    var description: String?
    var config: PipelineConfig?
    var isActive: Bool?
    var triggerMode: String?
    var scannerId: String?
    var signalSubscriptions: [SignalSubscription]?
    var notificationEnabled: Bool?
    var notificationEvents: [String]?
    var requireApproval: Bool?
    var approvalModes: [String]?
    var approvalTimeoutMinutes: Int?
    var approvalChannels: [String]?
    var approvalPhone: String?
}

struct PipelineList: Codable {
    let pipelines: [Pipeline]
    let total: Int
}

struct SignalSubscription: Codable {
    let signalType: String
    var timeframe: String?
    var minConfidence: Double?
}
