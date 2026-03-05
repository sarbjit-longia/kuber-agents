import Foundation
import UniformTypeIdentifiers

struct MultipartFormData {
    private let boundary: String
    private var body = Data()

    init(boundary: String = UUID().uuidString) {
        self.boundary = boundary
    }

    var contentType: String {
        "multipart/form-data; boundary=\(boundary)"
    }

    var data: Data {
        var result = body
        result.append("--\(boundary)--\r\n")
        return result
    }

    // MARK: - Append Text Field

    mutating func append(field name: String, value: String) {
        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n")
        body.append("\r\n")
        body.append("\(value)\r\n")
    }

    // MARK: - Append File Data

    mutating func append(fileData: Data, fieldName: String, fileName: String, mimeType: String? = nil) {
        let resolvedMimeType = mimeType ?? Self.mimeType(for: fileName)

        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"\(fileName)\"\r\n")
        body.append("Content-Type: \(resolvedMimeType)\r\n")
        body.append("\r\n")
        body.append(fileData)
        body.append("\r\n")
    }

    // MARK: - MIME Type Detection

    static func mimeType(for filename: String) -> String {
        let ext = (filename as NSString).pathExtension.lowercased()

        if let utType = UTType(filenameExtension: ext),
           let mimeType = utType.preferredMIMEType {
            return mimeType
        }

        // Fallback mapping for common types
        let fallback: [String: String] = [
            "pdf": "application/pdf",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "csv": "text/csv",
            "json": "application/json",
            "txt": "text/plain",
            "html": "text/html",
            "xml": "application/xml",
            "zip": "application/zip",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ]

        return fallback[ext] ?? "application/octet-stream"
    }
}

// MARK: - Data Extension for String Appending

private extension Data {
    mutating func append(_ string: String) {
        if let data = string.data(using: .utf8) {
            append(data)
        }
    }
}
