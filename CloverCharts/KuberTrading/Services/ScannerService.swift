import Foundation

actor ScannerService {
    static let shared = ScannerService()

    private init() {}

    // MARK: - List

    func listScanners() async throws -> [Scanner] {
        try await APIClient.shared.request(.listScanners)
    }

    // MARK: - Get

    func getScanner(id: String) async throws -> Scanner {
        try await APIClient.shared.request(.getScanner(id: id))
    }

    // MARK: - Create

    func createScanner(_ scanner: ScannerCreate) async throws -> Scanner {
        try await APIClient.shared.request(.createScanner(scanner))
    }

    // MARK: - Update

    func updateScanner(id: String, _ update: ScannerUpdate) async throws -> Scanner {
        try await APIClient.shared.request(.updateScanner(id: id, update))
    }

    // MARK: - Delete

    func deleteScanner(id: String) async throws {
        try await APIClient.shared.requestVoid(.deleteScanner(id: id))
    }

    // MARK: - Tickers

    func getScannerTickers(id: String) async throws -> ScannerTickersResponse {
        try await APIClient.shared.request(.getScannerTickers(id: id))
    }

    // MARK: - Usage

    func getScannerUsage(id: String) async throws -> ScannerUsageResponse {
        try await APIClient.shared.request(.getScannerUsage(id: id))
    }

    // MARK: - Signal Types

    func getSignalTypes() async throws -> [SignalType] {
        try await APIClient.shared.request(.getSignalTypes)
    }
}
