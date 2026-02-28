import Foundation
import OSLog

@Observable
final class ExecutionReportViewModel {
    var execution: Execution?
    var executiveReport: [String: AnyCodable]?
    var tradeAnalysis: [String: AnyCodable]?
    var isLoading = false
    var errorMessage: String?

    let executionId: String
    private let logger = Logger(subsystem: "com.kubertrading.app", category: "ExecutionReportVM")

    init(executionId: String) {
        self.executionId = executionId
    }

    // MARK: - Load Report

    @MainActor
    func loadReport() async {
        isLoading = true
        errorMessage = nil

        do {
            // Load execution, executive report, and trade analysis in parallel
            async let executionResult = ExecutionService.shared.getExecution(id: executionId)
            async let reportResult = ExecutionService.shared.getExecutiveReport(id: executionId)
            async let analysisResult = ExecutionService.shared.getTradeAnalysis(id: executionId)

            let (loadedExecution, loadedReport, loadedAnalysis) = try await (
                executionResult, reportResult, analysisResult
            )

            execution = loadedExecution
            executiveReport = loadedReport
            tradeAnalysis = loadedAnalysis
        } catch let error as APIError {
            // If trade analysis fails (e.g., no trade was made), still show what we have
            if executiveReport == nil {
                errorMessage = error.errorDescription
            }
            logger.error("Failed to load report: \(error.errorDescription ?? "Unknown")")

            // Try loading individually if parallel load failed
            if execution == nil {
                do { execution = try await ExecutionService.shared.getExecution(id: executionId) }
                catch { logger.error("Fallback execution load failed: \(error.localizedDescription)") }
            }
            if executiveReport == nil {
                do { executiveReport = try await ExecutionService.shared.getExecutiveReport(id: executionId) }
                catch { logger.error("Fallback report load failed: \(error.localizedDescription)") }
            }
            if tradeAnalysis == nil {
                do { tradeAnalysis = try await ExecutionService.shared.getTradeAnalysis(id: executionId) }
                catch { logger.debug("Trade analysis not available (may not have traded)") }
            }
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to load report: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Download PDF

    func downloadPDF() async throws -> Data {
        try await ExecutionService.shared.downloadReportPDF(id: executionId)
    }

    // MARK: - Computed Helpers (Extract Sections from Executive Report)

    var executiveSummary: [String: AnyCodable]? {
        extractSection("executive_summary") ?? extractSection("executiveSummary")
    }

    var aiAnalysis: [String: AnyCodable]? {
        extractSection("ai_analysis") ?? extractSection("aiAnalysis")
    }

    var strategyDetails: [String: AnyCodable]? {
        extractSection("strategy_details") ?? extractSection("strategyDetails")
            ?? extractSection("strategy")
    }

    var riskDetails: [String: AnyCodable]? {
        extractSection("risk_details") ?? extractSection("riskDetails")
            ?? extractSection("risk")
    }

    var tradeExecution: [String: AnyCodable]? {
        extractSection("trade_execution") ?? extractSection("tradeExecution")
            ?? extractSection("trade")
    }

    var pnlSummary: [String: AnyCodable]? {
        extractSection("pnl_summary") ?? extractSection("pnlSummary")
            ?? extractSection("pnl")
    }

    var agentReports: [[String: AnyCodable]]? {
        guard let report = executiveReport,
              let reportsValue = report["agent_reports"] ?? report["agentReports"],
              let array = reportsValue.arrayValue else {
            return nil
        }

        return array.compactMap { item -> [String: AnyCodable]? in
            guard let dict = item as? [String: Any] else { return nil }
            return dict.mapValues { AnyCodable($0) }
        }
    }

    var timeline: [[String: AnyCodable]]? {
        guard let report = executiveReport,
              let timelineValue = report["timeline"] ?? report["execution_timeline"]
                ?? report["executionTimeline"],
              let array = timelineValue.arrayValue else {
            return nil
        }

        return array.compactMap { item -> [String: AnyCodable]? in
            guard let dict = item as? [String: Any] else { return nil }
            return dict.mapValues { AnyCodable($0) }
        }
    }

    var costBreakdown: CostBreakdown? {
        execution?.costBreakdown
    }

    // MARK: - Private Helpers

    private func extractSection(_ key: String) -> [String: AnyCodable]? {
        guard let report = executiveReport,
              let sectionValue = report[key],
              let dict = sectionValue.dictValue else {
            return nil
        }
        return dict.mapValues { AnyCodable($0) }
    }
}
