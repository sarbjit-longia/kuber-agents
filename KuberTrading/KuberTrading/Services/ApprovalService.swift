import Foundation

actor ApprovalService {
    static let shared = ApprovalService()

    private init() {}

    // MARK: - Approve

    func approve(executionId: String, token: String) async throws {
        try await APIClient.shared.requestVoid(
            .approveExecution(executionId: executionId, token: token)
        )
    }

    // MARK: - Reject

    func reject(executionId: String, token: String) async throws {
        try await APIClient.shared.requestVoid(
            .rejectExecution(executionId: executionId, token: token)
        )
    }

    // MARK: - Pre-Trade Report

    func getPreTradeReport(executionId: String, token: String) async throws -> [String: AnyCodable] {
        try await APIClient.shared.request(
            .getPreTradeReport(executionId: executionId, token: token)
        )
    }
}
