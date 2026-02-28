import Foundation
import OSLog

@Observable
final class ApprovalViewModel {
    var preTradeReport: [String: AnyCodable]?
    var isLoading = false
    var errorMessage: String?
    var isActioned = false
    var actionResult: String? // "approved" or "rejected"

    // Countdown
    var expiresAt: Date?
    var timeRemaining: TimeInterval = 0
    private var countdownTask: Task<Void, Never>?

    let token: String
    let executionId: String?

    private let logger = Logger(subsystem: "com.kubertrading.app", category: "ApprovalVM")

    init(token: String, executionId: String? = nil) {
        self.token = token
        self.executionId = executionId
    }

    // MARK: - Load Pre-Trade Report

    @MainActor
    func loadPreTradeReport() async {
        guard let executionId else {
            errorMessage = "No execution ID provided."
            return
        }

        isLoading = true
        errorMessage = nil

        do {
            let report = try await ApprovalService.shared.getPreTradeReport(
                executionId: executionId,
                token: token
            )
            preTradeReport = report

            // Extract expiration from the report data
            if let expiresAtString = report["approval_expires_at"]?.stringValue
                ?? report["approvalExpiresAt"]?.stringValue {
                let formatter = ISO8601DateFormatter()
                formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                expiresAt = formatter.date(from: expiresAtString)
                    ?? ISO8601DateFormatter().date(from: expiresAtString)

                if expiresAt != nil {
                    startCountdown()
                }
            }
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to load pre-trade report: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to load pre-trade report: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Approve

    @MainActor
    func approve() async {
        guard let executionId else {
            errorMessage = "No execution ID provided."
            return
        }

        guard !isActioned else { return }

        isLoading = true
        errorMessage = nil

        do {
            try await ApprovalService.shared.approve(
                executionId: executionId,
                token: token
            )
            isActioned = true
            actionResult = "approved"
            stopCountdown()
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to approve: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to approve: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Reject

    @MainActor
    func reject() async {
        guard let executionId else {
            errorMessage = "No execution ID provided."
            return
        }

        guard !isActioned else { return }

        isLoading = true
        errorMessage = nil

        do {
            try await ApprovalService.shared.reject(
                executionId: executionId,
                token: token
            )
            isActioned = true
            actionResult = "rejected"
            stopCountdown()
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to reject: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to reject: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Countdown

    private func startCountdown() {
        countdownTask?.cancel()

        guard let expiresAt else {
            timeRemaining = 0
            return
        }

        timeRemaining = max(0, expiresAt.timeIntervalSince(Date()))

        countdownTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000) // 1 second
                guard !Task.isCancelled else { break }

                await MainActor.run {
                    guard let self, let expiresAt = self.expiresAt else { return }
                    self.timeRemaining = max(0, expiresAt.timeIntervalSince(Date()))
                    if self.timeRemaining <= 0 {
                        self.countdownTask?.cancel()
                    }
                }
            }
        }
    }

    private func stopCountdown() {
        countdownTask?.cancel()
        countdownTask = nil
    }

    // MARK: - Computed Properties

    var isExpired: Bool {
        timeRemaining <= 0 && expiresAt != nil
    }
}
