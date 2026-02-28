import Foundation
import OSLog

@Observable
final class PipelineListViewModel {
    var pipelines: [Pipeline] = []
    var isLoading = false
    var errorMessage: String?

    private let logger = Logger(subsystem: "com.kubertrading.app", category: "PipelineListVM")

    // MARK: - Load Pipelines

    @MainActor
    func loadPipelines() async {
        isLoading = true
        errorMessage = nil

        do {
            let response = try await PipelineService.shared.listPipelines()
            pipelines = response.pipelines
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to load pipelines: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to load pipelines: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Toggle Active

    @MainActor
    func toggleActive(pipeline: Pipeline) async {
        errorMessage = nil

        do {
            let updated = try await PipelineService.shared.toggleActive(
                id: pipeline.id,
                isActive: !pipeline.isActive
            )
            if let index = pipelines.firstIndex(where: { $0.id == updated.id }) {
                pipelines[index] = updated
            }
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to toggle pipeline: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Delete Pipeline

    @MainActor
    func deletePipeline(id: String) async {
        errorMessage = nil

        do {
            try await PipelineService.shared.deletePipeline(id: id)
            pipelines.removeAll { $0.id == id }
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to delete pipeline: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Execute Pipeline

    @MainActor
    func executePipeline(id: String, mode: String) async -> String? {
        errorMessage = nil

        do {
            let execution = try await ExecutionService.shared.createExecution(
                pipelineId: id,
                mode: mode
            )
            return execution.id
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to execute pipeline: \(error.errorDescription ?? "Unknown")")
            return nil
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }
}
