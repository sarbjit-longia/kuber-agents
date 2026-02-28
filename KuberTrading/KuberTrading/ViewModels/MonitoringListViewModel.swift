import Foundation
import OSLog

@Observable
final class MonitoringListViewModel {
    var executions: [ExecutionSummary] = []
    var stats: ExecutionStats?
    var isLoading = false
    var errorMessage: String?
    var total = 0

    // Filters
    var statusFilter: String?
    var pipelineIdFilter: String?
    var currentPage = 0
    var pageSize = 20

    private var isLoadingMore = false
    private let logger = Logger(subsystem: "com.kubertrading.app", category: "MonitoringListVM")

    // MARK: - Load Executions

    @MainActor
    func loadExecutions() async {
        isLoading = true
        errorMessage = nil

        do {
            let response = try await MonitoringService.shared.loadExecutions(
                limit: pageSize,
                offset: currentPage * pageSize,
                pipelineId: pipelineIdFilter,
                status: statusFilter
            )
            executions = response.executions
            total = response.total
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to load executions: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to load executions: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Load More (Pagination)

    @MainActor
    func loadMore() async {
        guard !isLoadingMore else { return }
        guard executions.count < total else { return }

        isLoadingMore = true
        currentPage += 1

        do {
            let response = try await MonitoringService.shared.loadExecutions(
                limit: pageSize,
                offset: currentPage * pageSize,
                pipelineId: pipelineIdFilter,
                status: statusFilter
            )
            executions.append(contentsOf: response.executions)
            total = response.total
        } catch let error as APIError {
            errorMessage = error.errorDescription
            currentPage = max(0, currentPage - 1) // Revert page on failure
            logger.error("Failed to load more executions: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            currentPage = max(0, currentPage - 1)
            logger.error("Failed to load more executions: \(error.localizedDescription)")
        }

        isLoadingMore = false
    }

    // MARK: - Load Stats

    @MainActor
    func loadStats() async {
        do {
            stats = try await MonitoringService.shared.loadExecutionStats()
        } catch let error as APIError {
            logger.error("Failed to load execution stats: \(error.errorDescription ?? "Unknown")")
        } catch {
            logger.error("Failed to load execution stats: \(error.localizedDescription)")
        }
    }

    // MARK: - Refresh

    @MainActor
    func refresh() async {
        currentPage = 0
        executions = []
        total = 0

        async let executionsLoad: Void = loadExecutions()
        async let statsLoad: Void = loadStats()
        _ = await (executionsLoad, statsLoad)
    }

    // MARK: - Set Status Filter

    @MainActor
    func setStatusFilter(_ status: String?) {
        statusFilter = status
        currentPage = 0
        executions = []
        total = 0

        Task {
            await loadExecutions()
        }
    }
}
