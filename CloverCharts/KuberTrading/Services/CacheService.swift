import Foundation
import SwiftData

@MainActor
final class CacheService {
    static let shared = CacheService()

    private var modelContext: ModelContext?

    private let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    private init() {}

    // MARK: - Configuration

    /// Must be called once at app launch with the shared ModelContext.
    func configure(with modelContext: ModelContext) {
        self.modelContext = modelContext
    }

    private func requireContext() throws -> ModelContext {
        guard let context = modelContext else {
            throw CacheError.notConfigured
        }
        return context
    }

    // MARK: - Dashboard

    func saveDashboard(_ dashboard: DashboardData, userId: String) throws {
        let context = try requireContext()
        let jsonData = try encoder.encode(dashboard)

        // Remove any existing cached dashboard for this user
        let descriptor = FetchDescriptor<CachedDashboard>(
            predicate: #Predicate { $0.userId == userId }
        )
        let existing = (try? context.fetch(descriptor)) ?? []
        for item in existing {
            context.delete(item)
        }

        let cached = CachedDashboard(userId: userId, jsonData: jsonData)
        context.insert(cached)
        try context.save()
    }

    func loadDashboard(userId: String) throws -> DashboardData? {
        let context = try requireContext()
        let descriptor = FetchDescriptor<CachedDashboard>(
            predicate: #Predicate { $0.userId == userId }
        )
        guard let cached = try context.fetch(descriptor).first else {
            return nil
        }
        guard !cached.isStale else {
            context.delete(cached)
            try context.save()
            return nil
        }
        return cached.decode()
    }

    // MARK: - Pipelines

    func savePipelines(_ pipelines: [Pipeline], userId: String) throws {
        let context = try requireContext()

        for pipeline in pipelines {
            let jsonData = try encoder.encode(pipeline)
            let pipelineId = pipeline.id

            let descriptor = FetchDescriptor<CachedPipeline>(
                predicate: #Predicate { $0.pipelineId == pipelineId }
            )
            let existing = (try? context.fetch(descriptor)) ?? []
            for item in existing {
                context.delete(item)
            }

            let cached = CachedPipeline(
                pipelineId: pipeline.id,
                userId: userId,
                jsonData: jsonData
            )
            context.insert(cached)
        }
        try context.save()
    }

    func savePipeline(_ pipeline: Pipeline, userId: String) throws {
        try savePipelines([pipeline], userId: userId)
    }

    func loadPipelines(userId: String) throws -> [Pipeline] {
        let context = try requireContext()
        let descriptor = FetchDescriptor<CachedPipeline>(
            predicate: #Predicate { $0.userId == userId }
        )
        let cached = try context.fetch(descriptor)
        return cached.compactMap { item -> Pipeline? in
            guard !item.isStale else { return nil }
            return item.decode()
        }
    }

    func loadPipeline(id: String) throws -> Pipeline? {
        let context = try requireContext()
        let descriptor = FetchDescriptor<CachedPipeline>(
            predicate: #Predicate { $0.pipelineId == id }
        )
        guard let cached = try context.fetch(descriptor).first else {
            return nil
        }
        guard !cached.isStale else {
            context.delete(cached)
            try context.save()
            return nil
        }
        return cached.decode()
    }

    func deletePipeline(id: String) throws {
        let context = try requireContext()
        let descriptor = FetchDescriptor<CachedPipeline>(
            predicate: #Predicate { $0.pipelineId == id }
        )
        let existing = (try? context.fetch(descriptor)) ?? []
        for item in existing {
            context.delete(item)
        }
        try context.save()
    }

    // MARK: - Executions

    func saveExecution(_ execution: Execution, userId: String) throws {
        let context = try requireContext()
        let jsonData = try encoder.encode(execution)
        let executionId = execution.id

        let descriptor = FetchDescriptor<CachedExecution>(
            predicate: #Predicate { $0.executionId == executionId }
        )
        let existing = (try? context.fetch(descriptor)) ?? []
        for item in existing {
            context.delete(item)
        }

        let cached = CachedExecution(
            executionId: execution.id,
            userId: userId,
            jsonData: jsonData,
            status: execution.status
        )
        context.insert(cached)
        try context.save()
    }

    func saveExecutions(_ executions: [Execution], userId: String) throws {
        for execution in executions {
            try saveExecution(execution, userId: userId)
        }
    }

    func loadExecution(id: String) throws -> Execution? {
        let context = try requireContext()
        let descriptor = FetchDescriptor<CachedExecution>(
            predicate: #Predicate { $0.executionId == id }
        )
        guard let cached = try context.fetch(descriptor).first else {
            return nil
        }
        return cached.decode()
    }

    func loadExecutions(userId: String, limit: Int = 50) throws -> [Execution] {
        let context = try requireContext()
        var descriptor = FetchDescriptor<CachedExecution>(
            predicate: #Predicate { $0.userId == userId }
        )
        descriptor.fetchLimit = limit
        let cached = try context.fetch(descriptor)
        return cached.compactMap { $0.decode() }
    }

    func deleteExecution(id: String) throws {
        let context = try requireContext()
        let descriptor = FetchDescriptor<CachedExecution>(
            predicate: #Predicate { $0.executionId == id }
        )
        let existing = (try? context.fetch(descriptor)) ?? []
        for item in existing {
            context.delete(item)
        }
        try context.save()
    }

    // MARK: - Scanners

    func saveScanners(_ scanners: [Scanner], userId: String) throws {
        let context = try requireContext()

        for scanner in scanners {
            let jsonData = try encoder.encode(scanner)
            let scannerId = scanner.id

            let descriptor = FetchDescriptor<CachedScanner>(
                predicate: #Predicate { $0.scannerId == scannerId }
            )
            let existing = (try? context.fetch(descriptor)) ?? []
            for item in existing {
                context.delete(item)
            }

            let cached = CachedScanner(
                scannerId: scanner.id,
                userId: userId,
                jsonData: jsonData
            )
            context.insert(cached)
        }
        try context.save()
    }

    func saveScanner(_ scanner: Scanner, userId: String) throws {
        try saveScanners([scanner], userId: userId)
    }

    func loadScanners(userId: String) throws -> [Scanner] {
        let context = try requireContext()
        let descriptor = FetchDescriptor<CachedScanner>(
            predicate: #Predicate { $0.userId == userId }
        )
        let cached = try context.fetch(descriptor)
        return cached.compactMap { item -> Scanner? in
            guard !item.isStale else { return nil }
            return item.decode()
        }
    }

    func loadScanner(id: String) throws -> Scanner? {
        let context = try requireContext()
        let descriptor = FetchDescriptor<CachedScanner>(
            predicate: #Predicate { $0.scannerId == id }
        )
        guard let cached = try context.fetch(descriptor).first else {
            return nil
        }
        guard !cached.isStale else {
            context.delete(cached)
            try context.save()
            return nil
        }
        return cached.decode()
    }

    func deleteScanner(id: String) throws {
        let context = try requireContext()
        let descriptor = FetchDescriptor<CachedScanner>(
            predicate: #Predicate { $0.scannerId == id }
        )
        let existing = (try? context.fetch(descriptor)) ?? []
        for item in existing {
            context.delete(item)
        }
        try context.save()
    }

    // MARK: - Clear All

    func clearAll() throws {
        let context = try requireContext()

        let dashboards = (try? context.fetch(FetchDescriptor<CachedDashboard>())) ?? []
        for item in dashboards { context.delete(item) }

        let pipelines = (try? context.fetch(FetchDescriptor<CachedPipeline>())) ?? []
        for item in pipelines { context.delete(item) }

        let executions = (try? context.fetch(FetchDescriptor<CachedExecution>())) ?? []
        for item in executions { context.delete(item) }

        let scanners = (try? context.fetch(FetchDescriptor<CachedScanner>())) ?? []
        for item in scanners { context.delete(item) }

        try context.save()
    }
}

// MARK: - Cache Error

enum CacheError: LocalizedError {
    case notConfigured

    var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "CacheService has not been configured with a ModelContext. Call configure(with:) at app launch."
        }
    }
}
