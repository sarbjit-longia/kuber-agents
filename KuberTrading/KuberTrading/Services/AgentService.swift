import Foundation

actor AgentService {
    static let shared = AgentService()

    private init() {}

    // MARK: - List

    func listAgents() async throws -> [AgentMetadata] {
        try await APIClient.shared.request(.listAgents)
    }

    // MARK: - By Category

    func getAgentsByCategory(category: String) async throws -> [AgentMetadata] {
        try await APIClient.shared.request(.getAgentsByCategory(category: category))
    }

    // MARK: - Get Single

    func getAgent(agentType: String) async throws -> AgentMetadata {
        try await APIClient.shared.request(.getAgent(agentType: agentType))
    }

    // MARK: - Validate Instructions

    func validateInstructions(
        agentType: String,
        instructions: String,
        documentUrl: String? = nil
    ) async throws -> ValidateInstructionsResponse {
        let request = ValidateInstructionsRequest(
            agentType: agentType,
            instructions: instructions,
            documentUrl: documentUrl
        )
        return try await APIClient.shared.request(.validateInstructions(request))
    }

    // MARK: - Available Tools

    func getAvailableTools() async throws -> AvailableToolsResponse {
        try await APIClient.shared.request(.getAvailableTools)
    }
}
