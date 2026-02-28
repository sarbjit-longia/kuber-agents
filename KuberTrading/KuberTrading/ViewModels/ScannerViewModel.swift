import Foundation
import OSLog

@Observable
final class ScannerViewModel {
    var scanners: [Scanner] = []
    var isLoading = false
    var errorMessage: String?
    var showCreateSheet = false

    // Create/Edit form
    var editingScanner: Scanner?
    var scannerName = ""
    var scannerDescription = ""
    var scannerType = "manual"
    var tickers: [String] = []
    var tickerInput = ""

    private let logger = Logger(subsystem: "com.kubertrading.app", category: "ScannerVM")

    // MARK: - Load Scanners

    @MainActor
    func loadScanners() async {
        isLoading = true
        errorMessage = nil

        do {
            scanners = try await ScannerService.shared.listScanners()
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to load scanners: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to load scanners: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Create Scanner

    @MainActor
    func createScanner() async {
        guard !scannerName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            errorMessage = "Scanner name is required."
            return
        }

        isLoading = true
        errorMessage = nil

        do {
            var config: [String: AnyCodable] = [:]
            if !tickers.isEmpty {
                config["tickers"] = AnyCodable(tickers)
            }

            let scannerCreate = ScannerCreate(
                name: scannerName.trimmingCharacters(in: .whitespacesAndNewlines),
                description: scannerDescription.isEmpty ? nil : scannerDescription,
                scannerType: scannerType,
                config: config,
                isActive: true,
                refreshInterval: nil
            )

            let newScanner = try await ScannerService.shared.createScanner(scannerCreate)
            scanners.append(newScanner)
            resetForm()
            showCreateSheet = false
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to create scanner: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to create scanner: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Update Scanner

    @MainActor
    func updateScanner() async {
        guard let scanner = editingScanner else {
            errorMessage = "No scanner selected for editing."
            return
        }

        guard !scannerName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            errorMessage = "Scanner name is required."
            return
        }

        isLoading = true
        errorMessage = nil

        do {
            var config: [String: AnyCodable] = scanner.config
            config["tickers"] = AnyCodable(tickers)

            let scannerUpdate = ScannerUpdate(
                name: scannerName.trimmingCharacters(in: .whitespacesAndNewlines),
                description: scannerDescription.isEmpty ? nil : scannerDescription,
                config: config,
                isActive: nil,
                refreshInterval: nil
            )

            let updated = try await ScannerService.shared.updateScanner(id: scanner.id, scannerUpdate)

            if let index = scanners.firstIndex(where: { $0.id == updated.id }) {
                scanners[index] = updated
            }

            resetForm()
            showCreateSheet = false
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to update scanner: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to update scanner: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Delete Scanner

    @MainActor
    func deleteScanner(id: String) async {
        errorMessage = nil

        do {
            try await ScannerService.shared.deleteScanner(id: id)
            scanners.removeAll { $0.id == id }
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to delete scanner: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Check Usage

    func checkUsage(id: String) async throws -> ScannerUsageResponse {
        try await ScannerService.shared.getScannerUsage(id: id)
    }

    // MARK: - Ticker Management

    func addTicker() {
        let ticker = tickerInput.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !ticker.isEmpty else { return }
        guard !tickers.contains(ticker) else {
            tickerInput = ""
            return
        }
        tickers.append(ticker)
        tickerInput = ""
    }

    func removeTicker(at index: Int) {
        guard index >= 0 && index < tickers.count else { return }
        tickers.remove(at: index)
    }

    // MARK: - Form Management

    func resetForm() {
        editingScanner = nil
        scannerName = ""
        scannerDescription = ""
        scannerType = "manual"
        tickers = []
        tickerInput = ""
        errorMessage = nil
    }

    func prepareEdit(scanner: Scanner) {
        editingScanner = scanner
        scannerName = scanner.name
        scannerDescription = scanner.description ?? ""
        scannerType = scanner.scannerType

        // Extract tickers from config
        if let tickersValue = scanner.config["tickers"],
           let tickerArray = tickersValue.arrayValue as? [String] {
            tickers = tickerArray
        } else {
            tickers = []
        }

        tickerInput = ""
        showCreateSheet = true
    }
}
