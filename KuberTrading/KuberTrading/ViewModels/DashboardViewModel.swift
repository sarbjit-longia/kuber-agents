import Foundation
import OSLog

@Observable
final class DashboardViewModel {
    var data: DashboardData?
    var isLoading = false
    var errorMessage: String?
    var lastUpdated: Date?

    // Chart period selectors
    var pnlChartDays = 7
    var costChartDays = 7

    private var autoRefreshTask: Task<Void, Never>?
    private let logger = Logger(subsystem: "com.kubertrading.app", category: "DashboardVM")

    // MARK: - Load Dashboard

    @MainActor
    func loadDashboard() async {
        isLoading = data == nil // Only show loading spinner on initial load
        errorMessage = nil

        do {
            let dashboardData = try await DashboardService.shared.loadDashboard()
            data = dashboardData
            lastUpdated = Date()
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Dashboard load failed: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Dashboard load failed: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Auto Refresh

    func startAutoRefresh() {
        stopAutoRefresh()
        autoRefreshTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 30_000_000_000) // 30 seconds
                guard !Task.isCancelled else { break }
                await self?.loadDashboard()
            }
        }
    }

    func stopAutoRefresh() {
        autoRefreshTask?.cancel()
        autoRefreshTask = nil
    }

    // MARK: - Chart Data Helpers

    var pnlChartData: [PnLHistoryEntry] {
        guard let history = data?.pnlHistory else { return [] }
        if history.count <= pnlChartDays {
            return history
        }
        return Array(history.suffix(pnlChartDays))
    }

    var costChartData: [CostHistoryEntry] {
        guard let history = data?.costHistory else { return [] }
        if history.count <= costChartDays {
            return history
        }
        return Array(history.suffix(costChartDays))
    }
}
