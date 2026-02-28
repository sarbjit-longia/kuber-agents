import Foundation

// MARK: - Response Wrapper

struct ExecutionListResponse: Codable {
    let executions: [ExecutionSummary]
    let total: Int
    let activeCount: Int?
    let historicalTotal: Int?
    let limit: Int?
    let offset: Int?
}

// MARK: - File Upload Response

struct FileUploadResponse: Codable {
    let filename: String
    let path: String
    let size: Int
}

// MARK: - Service

actor ExecutionService {
    static let shared = ExecutionService()

    private init() {}

    // MARK: - Create

    func createExecution(pipelineId: String, mode: String?) async throws -> Execution {
        let request = ExecutionCreate(pipelineId: pipelineId, mode: mode)
        return try await APIClient.shared.request(.createExecution(request))
    }

    // MARK: - List

    func listExecutions(
        limit: Int? = 50,
        offset: Int? = 0,
        pipelineId: String? = nil,
        status: String? = nil
    ) async throws -> ExecutionListResponse {
        try await APIClient.shared.request(
            .listExecutions(limit: limit, offset: offset, pipelineId: pipelineId, status: status)
        )
    }

    // MARK: - Get

    func getExecution(id: String) async throws -> Execution {
        try await APIClient.shared.request(.getExecution(id: id))
    }

    // MARK: - Stats

    func getExecutionStats() async throws -> ExecutionStats {
        try await APIClient.shared.request(.getExecutionStats)
    }

    // MARK: - Lifecycle Actions

    func stopExecution(id: String) async throws {
        try await APIClient.shared.requestVoid(.stopExecution(id: id))
    }

    func closePosition(id: String) async throws {
        try await APIClient.shared.requestVoid(.closePosition(id: id))
    }

    func reconcileExecution(id: String) async throws {
        try await APIClient.shared.requestVoid(.reconcileExecution(id: id))
    }

    func resumeMonitoring(id: String) async throws {
        try await APIClient.shared.requestVoid(.resumeMonitoring(id: id))
    }

    func pauseExecution(id: String) async throws {
        try await APIClient.shared.requestVoid(.pauseExecution(id: id))
    }

    func resumeExecution(id: String) async throws {
        try await APIClient.shared.requestVoid(.resumeExecution(id: id))
    }

    func cancelExecution(id: String) async throws {
        try await APIClient.shared.requestVoid(.cancelExecution(id: id))
    }

    // MARK: - Logs

    func getExecutionLogs(id: String) async throws -> [ExecutionLog] {
        try await APIClient.shared.request(.getExecutionLogs(id: id))
    }

    // MARK: - Reports & Analysis

    func getExecutiveReport(id: String) async throws -> [String: AnyCodable] {
        try await APIClient.shared.request(.getExecutiveReport(id: id))
    }

    func getTradeAnalysis(id: String) async throws -> [String: AnyCodable] {
        try await APIClient.shared.request(.getTradeAnalysis(id: id))
    }

    func downloadReportPDF(id: String) async throws -> Data {
        try await APIClient.shared.requestRaw(.downloadReportPDF(id: id))
    }
}
