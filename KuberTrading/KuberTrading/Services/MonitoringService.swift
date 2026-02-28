import Foundation

actor MonitoringService {
    static let shared = MonitoringService()

    private init() {}

    // MARK: - Executions (delegates to ExecutionService)

    /// Loads a page of executions, optionally filtered by pipeline or status.
    func loadExecutions(
        limit: Int = 50,
        offset: Int = 0,
        pipelineId: String? = nil,
        status: String? = nil
    ) async throws -> ExecutionListResponse {
        try await ExecutionService.shared.listExecutions(
            limit: limit,
            offset: offset,
            pipelineId: pipelineId,
            status: status
        )
    }

    // MARK: - Stats (delegates to ExecutionService)

    /// Loads aggregate execution statistics for the monitoring dashboard.
    func loadExecutionStats() async throws -> ExecutionStats {
        try await ExecutionService.shared.getExecutionStats()
    }
}
