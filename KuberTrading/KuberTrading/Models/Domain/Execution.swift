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
