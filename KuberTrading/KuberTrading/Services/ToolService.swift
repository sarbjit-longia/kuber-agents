import Foundation

actor ToolService {
    static let shared = ToolService()

    private init() {}

    // MARK: - List

    func listTools() async throws -> [ToolMetadata] {
        try await APIClient.shared.request(.listTools)
    }

    // MARK: - By Category

    func getToolsByCategory(category: String) async throws -> [ToolMetadata] {
        try await APIClient.shared.request(.getToolsByCategory(category: category))
    }

    // MARK: - Get Single

    func getTool(toolType: String) async throws -> ToolMetadata {
        try await APIClient.shared.request(.getTool(toolType: toolType))
    }
}
