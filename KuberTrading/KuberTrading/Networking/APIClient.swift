import Foundation
import OSLog

actor APIClient {
    static let shared = APIClient()

    private let session: URLSession
    private let baseURL: URL
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    private let logger = Logger(subsystem: "com.kubertrading.app", category: "APIClient")

    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 300
        config.waitsForConnectivity = true
        self.session = URLSession(configuration: config)
        self.baseURL = AppConfiguration.shared.apiBaseURL

        self.decoder = JSONDecoder()
        self.decoder.keyDecodingStrategy = .convertFromSnakeCase

        self.encoder = JSONEncoder()
        self.encoder.keyEncodingStrategy = .convertToSnakeCase
    }

    // MARK: - Public Request Methods

    /// Performs a request and decodes the response into the specified `Decodable` type.
    func request<T: Decodable>(_ endpoint: APIEndpoint) async throws -> T {
        let request = try await buildRequest(for: endpoint)
        let (data, response) = try await performRequest(request)
        try validateResponse(response, data: data)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            logger.error("Decoding error for \(endpoint.path): \(error.localizedDescription)")
            throw APIError.decodingError(error)
        }
    }

    /// Performs a request and returns the raw response `Data` (for PDF downloads, etc.).
    func requestRaw(_ endpoint: APIEndpoint) async throws -> Data {
        let request = try await buildRequest(for: endpoint)
        let (data, response) = try await performRequest(request)
        try validateResponse(response, data: data)
        return data
    }

    /// Performs a request that does not return a meaningful body (fire-and-forget style).
    func requestVoid(_ endpoint: APIEndpoint) async throws {
        let request = try await buildRequest(for: endpoint)
        let (data, response) = try await performRequest(request)
        try validateResponse(response, data: data)
    }

    // MARK: - Build Request

    private func buildRequest(for endpoint: APIEndpoint) async throws -> URLRequest {
        // Build the URL from base path + endpoint path
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent(endpoint.path),
            resolvingAgainstBaseURL: true
        ) else {
            throw APIError.invalidURL
        }

        // Attach query items if present
        if let queryItems = endpoint.queryItems {
            components.queryItems = queryItems
        }

        guard let url = components.url else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method.rawValue

        // Authorization header
        if endpoint.requiresAuth {
            let token = try await KeychainService.shared.read(.accessToken)
            guard let token, !token.isEmpty else {
                throw APIError.unauthorized
            }
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        // Handle body encoding based on endpoint type
        if endpoint.isFormEncoded {
            try encodeFormBody(for: endpoint, into: &request)
        } else if endpoint.isMultipart {
            try encodeMultipartBody(for: endpoint, into: &request)
        } else if let body = endpoint.body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try encoder.encode(AnyEncodable(body))
        }

        // Accept header
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        return request
    }

    // MARK: - Form-Encoded Body (OAuth2 Login)

    /// FastAPI OAuth2PasswordRequestForm expects `application/x-www-form-urlencoded`
    /// with fields `username` (the email) and `password`.
    private func encodeFormBody(for endpoint: APIEndpoint, into request: inout URLRequest) throws {
        guard case .login(let credentials) = endpoint else { return }

        request.setValue(
            "application/x-www-form-urlencoded",
            forHTTPHeaderField: "Content-Type"
        )

        var components = URLComponents()
        components.queryItems = [
            URLQueryItem(name: "username", value: credentials.email),
            URLQueryItem(name: "password", value: credentials.password),
        ]

        // percentEncodedQuery already handles proper encoding
        request.httpBody = components.percentEncodedQuery?.data(using: .utf8)
    }

    // MARK: - Multipart Body (File Upload)

    private func encodeMultipartBody(for endpoint: APIEndpoint, into request: inout URLRequest) throws {
        guard let multipart = endpoint.multipartData else { return }

        var formData = MultipartFormData()
        formData.append(
            fileData: multipart.data,
            fieldName: "file",
            fileName: multipart.filename
        )

        request.setValue(formData.contentType, forHTTPHeaderField: "Content-Type")
        request.httpBody = formData.data
    }

    // MARK: - Perform Request with Retry

    private func performRequest(_ request: URLRequest) async throws -> (Data, URLResponse) {
        do {
            return try await session.data(for: request)
        } catch let error as URLError {
            logger.error("Network error: \(error.localizedDescription)")
            throw APIError.networkError(error)
        } catch {
            logger.error("Unexpected error: \(error.localizedDescription)")
            throw APIError.networkError(error)
        }
    }

    // MARK: - Validate Response

    private func validateResponse(_ response: URLResponse, data: Data) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.noData
        }

        let statusCode = httpResponse.statusCode

        switch statusCode {
        case 200...299:
            return
        case 401:
            logger.warning("Unauthorized response received")
            throw APIError.unauthorized
        case 403:
            throw APIError.forbidden
        case 404:
            throw APIError.notFound
        case 422:
            if let errorResponse = try? decoder.decode(APIErrorResponse.self, from: data) {
                throw APIError.validationError(detail: errorResponse.detail ?? "Validation error")
            }
            throw APIError.validationError(detail: "Validation error")
        default:
            let errorResponse = try? decoder.decode(APIErrorResponse.self, from: data)
            logger.error("Server error \(statusCode): \(errorResponse?.detail ?? "Unknown")")
            throw APIError.serverError(statusCode: statusCode, message: errorResponse?.detail)
        }
    }
}

// MARK: - AnyEncodable Wrapper

/// Type-erased `Encodable` wrapper used to encode the heterogeneous `body` property
/// from `APIEndpoint` into JSON data.
private struct AnyEncodable: Encodable {
    private let encodeClosure: (Encoder) throws -> Void

    init(_ wrapped: any Encodable) {
        self.encodeClosure = { encoder in
            try wrapped.encode(to: encoder)
        }
    }

    func encode(to encoder: Encoder) throws {
        try encodeClosure(encoder)
    }
}
