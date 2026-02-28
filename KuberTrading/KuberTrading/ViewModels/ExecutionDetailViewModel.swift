import Foundation
import OSLog

@Observable
final class ExecutionDetailViewModel {
    var execution: Execution?
    var logs: [ExecutionLog] = []
    var isLoading = false
    var errorMessage: String?

    // Approval countdown
    var approvalTimeRemaining: TimeInterval = 0
    var approvalCountdownTask: Task<Void, Never>?

    // Auto-refresh
    private var autoRefreshTask: Task<Void, Never>?
    private var wsStreamTask: Task<Void, Never>?
    private var wsManager = WebSocketManager.shared

    let executionId: String
    private let logger = Logger(subsystem: "com.kubertrading.app", category: "ExecutionDetailVM")

    init(executionId: String) {
        self.executionId = executionId
    }

    // MARK: - Load Execution

    @MainActor
    func loadExecution() async {
        isLoading = execution == nil
        errorMessage = nil

        do {
            execution = try await ExecutionService.shared.getExecution(id: executionId)

            // Start approval countdown if needed
            if showApprovalBanner {
                startApprovalCountdown()
            }
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to load execution: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to load execution: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Load Logs

    @MainActor
    func loadLogs() async {
        do {
            logs = try await ExecutionService.shared.getExecutionLogs(id: executionId)
        } catch let error as APIError {
            logger.error("Failed to load logs: \(error.errorDescription ?? "Unknown")")
        } catch {
            logger.error("Failed to load logs: \(error.localizedDescription)")
        }
    }

    // MARK: - Live Updates

    func startLiveUpdates() {
        // Subscribe to WebSocket updates
        wsManager.subscribeToExecution(executionId)

        wsStreamTask = Task { [weak self] in
            guard let self else { return }
            let stream = self.wsManager.messageStream()

            for await message in stream {
                guard !Task.isCancelled else { break }
                if message.executionId == self.executionId {
                    await MainActor.run {
                        // Update execution status from WebSocket messages
                        if message.type == "status_update",
                           let data = message.data?.dictValue,
                           let newStatus = data["status"] as? String {
                            self.execution?.status = newStatus.lowercased()
                        }

                        // Append log messages
                        if message.type == "log" {
                            let log = ExecutionLog(
                                executionId: self.executionId,
                                timestamp: message.timestamp ?? ISO8601DateFormatter().string(from: Date()),
                                level: "info",
                                agentType: nil,
                                message: message.message ?? "",
                                details: message.data
                            )
                            self.logs.append(log)
                        }

                        // Handle completion
                        if message.type == "execution_complete" || message.type == "execution_failed" {
                            Task {
                                await self.loadExecution()
                            }
                        }
                    }
                }
            }
        }

        // Auto-refresh every 10 seconds as a fallback
        autoRefreshTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 10_000_000_000) // 10 seconds
                guard !Task.isCancelled else { break }
                guard let self, self.isActive else { break }
                await self.loadExecution()
                await self.loadLogs()
            }
        }
    }

    func stopLiveUpdates() {
        wsManager.unsubscribeFromExecution(executionId)
        wsStreamTask?.cancel()
        wsStreamTask = nil
        autoRefreshTask?.cancel()
        autoRefreshTask = nil
        approvalCountdownTask?.cancel()
        approvalCountdownTask = nil
    }

    // MARK: - Actions

    @MainActor
    func approveExecution() async {
        errorMessage = nil

        do {
            // Use the execution's approval mechanism via the standard execution endpoint
            // The backend handles the approval through the execution service
            try await APIClient.shared.requestVoid(
                .approveExecution(executionId: executionId, token: "")
            )
            await loadExecution()
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to approve execution: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func rejectExecution() async {
        errorMessage = nil

        do {
            try await APIClient.shared.requestVoid(
                .rejectExecution(executionId: executionId, token: "")
            )
            await loadExecution()
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to reject execution: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func closePosition() async {
        errorMessage = nil

        do {
            try await ExecutionService.shared.closePosition(id: executionId)
            await loadExecution()
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to close position: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func stopExecution() async {
        errorMessage = nil

        do {
            try await ExecutionService.shared.stopExecution(id: executionId)
            await loadExecution()
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to stop execution: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func cancelExecution() async {
        errorMessage = nil

        do {
            try await ExecutionService.shared.cancelExecution(id: executionId)
            await loadExecution()
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to cancel execution: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Approval Countdown

    private func startApprovalCountdown() {
        approvalCountdownTask?.cancel()

        guard let expiresAtString = execution?.approvalExpiresAt else {
            approvalTimeRemaining = 0
            return
        }

        // Parse the expiration date
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let expiresAt: Date?

        expiresAt = formatter.date(from: expiresAtString)
            ?? ISO8601DateFormatter().date(from: expiresAtString)

        guard let expirationDate = expiresAt else {
            approvalTimeRemaining = 0
            return
        }

        approvalTimeRemaining = expirationDate.timeIntervalSince(Date())

        approvalCountdownTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000) // 1 second
                guard !Task.isCancelled else { break }

                await MainActor.run {
                    guard let self else { return }
                    self.approvalTimeRemaining = max(0, expirationDate.timeIntervalSince(Date()))
                    if self.approvalTimeRemaining <= 0 {
                        self.approvalCountdownTask?.cancel()
                    }
                }
            }
        }
    }

    // MARK: - Computed Properties

    var isActive: Bool {
        guard let status = execution?.status else { return false }
        return ["running", "monitoring", "awaiting_approval"].contains(status)
    }

    var showApprovalBanner: Bool {
        execution?.status == "awaiting_approval"
            && execution?.approvalStatus != "approved"
            && execution?.approvalStatus != "rejected"
    }

    var showMonitoringBanner: Bool {
        execution?.status == "monitoring"
    }
}
