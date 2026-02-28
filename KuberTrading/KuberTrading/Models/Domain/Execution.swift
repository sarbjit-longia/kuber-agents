import Foundation

// MARK: - Full Execution (detail endpoint)

struct Execution: Codable, Identifiable {
    let id: String
    let pipelineId: String
    let pipelineName: String?
    let userId: String?
    var status: String
    let mode: String
    let symbol: String?
    let triggerMode: String?
    let scannerName: String?
    let startedAt: String?
    var completedAt: String?
    var errorMessage: String?
    var result: AnyCodable?
    var costBreakdown: CostBreakdown?
    var agentStates: [AgentState]?
    var logs: [ExecutionLog]?
    var reports: [String: AgentReport]?
    var executionArtifacts: AnyCodable?
    var approvalStatus: String?
    var approvalRequestedAt: String?
    var approvalExpiresAt: String?
    let createdAt: String?
    let updatedAt: String?
    let cost: Double?
    // Detail-only fields
    let executionPhase: String?
    let nextCheckAt: String?
    let monitorIntervalMinutes: Int?
    let pipelineConfig: AnyCodable?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        pipelineId = try container.decode(String.self, forKey: .pipelineId)
        pipelineName = try container.decodeIfPresent(String.self, forKey: .pipelineName)
        userId = try container.decodeIfPresent(String.self, forKey: .userId)
        status = (try container.decode(String.self, forKey: .status)).lowercased()
        mode = try container.decode(String.self, forKey: .mode)
        symbol = try container.decodeIfPresent(String.self, forKey: .symbol)
        triggerMode = try container.decodeIfPresent(String.self, forKey: .triggerMode)
        scannerName = try container.decodeIfPresent(String.self, forKey: .scannerName)
        startedAt = try container.decodeIfPresent(String.self, forKey: .startedAt)
        completedAt = try container.decodeIfPresent(String.self, forKey: .completedAt)
        errorMessage = try container.decodeIfPresent(String.self, forKey: .errorMessage)
        result = try container.decodeIfPresent(AnyCodable.self, forKey: .result)
        costBreakdown = try container.decodeIfPresent(CostBreakdown.self, forKey: .costBreakdown)
        agentStates = try container.decodeIfPresent([AgentState].self, forKey: .agentStates)
        logs = try container.decodeIfPresent([ExecutionLog].self, forKey: .logs)
        reports = try container.decodeIfPresent([String: AgentReport].self, forKey: .reports)
        executionArtifacts = try container.decodeIfPresent(AnyCodable.self, forKey: .executionArtifacts)
        approvalStatus = try container.decodeIfPresent(String.self, forKey: .approvalStatus)
        approvalRequestedAt = try container.decodeIfPresent(String.self, forKey: .approvalRequestedAt)
        approvalExpiresAt = try container.decodeIfPresent(String.self, forKey: .approvalExpiresAt)
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
        updatedAt = try container.decodeIfPresent(String.self, forKey: .updatedAt)
        cost = try container.decodeIfPresent(Double.self, forKey: .cost)
        executionPhase = try container.decodeIfPresent(String.self, forKey: .executionPhase)
        nextCheckAt = try container.decodeIfPresent(String.self, forKey: .nextCheckAt)
        monitorIntervalMinutes = try container.decodeIfPresent(Int.self, forKey: .monitorIntervalMinutes)
        pipelineConfig = try container.decodeIfPresent(AnyCodable.self, forKey: .pipelineConfig)
    }
}

// MARK: - Execution Summary (list endpoint)

struct ExecutionSummary: Codable, Identifiable {
    let id: String
    let pipelineId: String
    let pipelineName: String?
    let status: String
    let mode: String
    let symbol: String?
    let triggerMode: String?
    let scannerName: String?
    let startedAt: String?
    let completedAt: String?
    let durationSeconds: Double?
    let totalCost: Double?
    let agentCount: Int?
    let agentsCompleted: Int?
    let errorMessage: String?
    let strategyAction: String?
    let strategyConfidence: Double?
    let tradeOutcome: String?
    let result: AnyCodable?
    let reports: AnyCodable?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        pipelineId = try container.decode(String.self, forKey: .pipelineId)
        pipelineName = try container.decodeIfPresent(String.self, forKey: .pipelineName)
        status = (try container.decode(String.self, forKey: .status)).lowercased()
        mode = try container.decode(String.self, forKey: .mode)
        symbol = try container.decodeIfPresent(String.self, forKey: .symbol)
        triggerMode = try container.decodeIfPresent(String.self, forKey: .triggerMode)
        scannerName = try container.decodeIfPresent(String.self, forKey: .scannerName)
        startedAt = try container.decodeIfPresent(String.self, forKey: .startedAt)
        completedAt = try container.decodeIfPresent(String.self, forKey: .completedAt)
        durationSeconds = try container.decodeIfPresent(Double.self, forKey: .durationSeconds)
        totalCost = try container.decodeIfPresent(Double.self, forKey: .totalCost)
        agentCount = try container.decodeIfPresent(Int.self, forKey: .agentCount)
        agentsCompleted = try container.decodeIfPresent(Int.self, forKey: .agentsCompleted)
        errorMessage = try container.decodeIfPresent(String.self, forKey: .errorMessage)
        strategyAction = try container.decodeIfPresent(String.self, forKey: .strategyAction)
        strategyConfidence = try container.decodeIfPresent(Double.self, forKey: .strategyConfidence)
        tradeOutcome = try container.decodeIfPresent(String.self, forKey: .tradeOutcome)
        result = try container.decodeIfPresent(AnyCodable.self, forKey: .result)
        reports = try container.decodeIfPresent(AnyCodable.self, forKey: .reports)
    }
}

// MARK: - Cost Breakdown

struct CostBreakdown: Codable {
    let totalCost: Double?
    let llmCost: Double?
    let agentRentalCost: Double?
    let apiCallCost: Double?
    let byAgent: [String: Double]?
}

// MARK: - Agent State

struct AgentState: Codable, Identifiable {
    var id: String { agentId ?? UUID().uuidString }
    let agentId: String?
    let agentType: String?
    let agentName: String?
    var status: String?
    let startedAt: String?
    let completedAt: String?
    let errorMessage: String?
    let output: AnyCodable?
    let cost: Double?
}

// MARK: - Execution Log

struct ExecutionLog: Codable, Identifiable {
    var id: String { "\(executionId ?? "")-\(timestamp ?? "")-\(message.prefix(20))" }
    let executionId: String?
    let timestamp: String?
    let level: String?
    let agentType: String?
    let message: String
    let details: AnyCodable?
}

// MARK: - Agent Report

struct AgentReport: Codable {
    let agentId: String?
    let agentType: String?
    let title: String?
    let summary: String?
    let status: String?
    let details: String?
    let metrics: [AgentReportMetric]?
    let data: AnyCodable?
    let createdAt: String?
}

struct AgentReportMetric: Codable {
    let label: String
    let value: AnyCodable
    let type: String?
}

// MARK: - Execution Stats

struct ExecutionStats: Codable {
    let totalExecutions: Int?
    let runningExecutions: Int?
    let completedExecutions: Int?
    let failedExecutions: Int?
    let totalCost: Double?
    let avgDurationSeconds: Double?
    let successRate: Double?
}

// MARK: - Execution Create Request

struct ExecutionCreate: Codable {
    let pipelineId: String
    let mode: String?
}
