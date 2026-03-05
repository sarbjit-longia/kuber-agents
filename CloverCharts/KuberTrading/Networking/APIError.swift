import Foundation

enum APIError: LocalizedError {
    case invalidURL
    case unauthorized
    case forbidden
    case notFound
    case validationError(detail: String)
    case serverError(statusCode: Int, message: String?)
    case networkError(Error)
    case decodingError(Error)
    case noData
    case unknown(statusCode: Int)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .unauthorized:
            return "Session expired. Please log in again."
        case .forbidden:
            return "You don't have permission to perform this action."
        case .notFound:
            return "The requested resource was not found."
        case .validationError(let detail):
            return detail
        case .serverError(_, let message):
            return message ?? "An unexpected server error occurred."
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .decodingError(let error):
            return "Failed to process server response: \(error.localizedDescription)"
        case .noData:
            return "No data received from server."
        case .unknown(let statusCode):
            return "Unexpected error (HTTP \(statusCode))."
        }
    }

    var isAuthError: Bool {
        if case .unauthorized = self { return true }
        return false
    }
}

struct APIErrorResponse: Decodable {
    let detail: String?
}
