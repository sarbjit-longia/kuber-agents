import Foundation

actor FileService {
    static let shared = FileService()

    private init() {}

    // MARK: - Upload

    func uploadFile(data: Data, filename: String) async throws -> FileUploadResponse {
        try await APIClient.shared.request(.uploadFile(data, filename: filename))
    }

    // MARK: - Download

    func downloadFile(path: String) async throws -> Data {
        try await APIClient.shared.requestRaw(.downloadFile(path: path))
    }

    // MARK: - Delete

    func deleteFile(path: String) async throws {
        try await APIClient.shared.requestVoid(.deleteFile(path: path))
    }
}
