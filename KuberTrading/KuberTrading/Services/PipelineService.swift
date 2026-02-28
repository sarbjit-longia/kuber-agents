import Foundation

actor PipelineService {
    static let shared = PipelineService()

    private init() {}

    // MARK: - List

    func listPipelines() async throws -> PipelineList {
        try await APIClient.shared.request(.listPipelines)
    }

    // MARK: - Get

    func getPipeline(id: String) async throws -> Pipeline {
        try await APIClient.shared.request(.getPipeline(id: id))
    }

    // MARK: - Create

    func createPipeline(_ pipeline: PipelineCreate) async throws -> Pipeline {
        try await APIClient.shared.request(.createPipeline(pipeline))
    }

    // MARK: - Update

    func updatePipeline(id: String, _ update: PipelineUpdate) async throws -> Pipeline {
        try await APIClient.shared.request(.updatePipeline(id: id, update))
    }

    // MARK: - Delete

    func deletePipeline(id: String) async throws {
        try await APIClient.shared.requestVoid(.deletePipeline(id: id))
    }

    // MARK: - Toggle Active

    /// Convenience method that toggles the `isActive` flag on a pipeline.
    func toggleActive(id: String, isActive: Bool) async throws -> Pipeline {
        let update = PipelineUpdate(isActive: isActive)
        return try await updatePipeline(id: id, update)
    }
}
