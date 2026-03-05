import Foundation

extension String {
    var isValidEmail: Bool {
        guard let regex = try? Regex("^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$") else { return false }
        return wholeMatch(of: regex) != nil
    }

    var isValidPassword: Bool {
        count >= 8
    }

    var isValidPhone: Bool {
        guard let regex = try? Regex("^\\+?[\\d\\s\\-()]{7,15}$") else { return false }
        return wholeMatch(of: regex) != nil
    }

    var trimmed: String {
        trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var nilIfEmpty: String? {
        trimmed.isEmpty ? nil : trimmed
    }

    func truncated(to maxLength: Int, trailing: String = "...") -> String {
        if count <= maxLength { return self }
        return String(prefix(maxLength)) + trailing
    }
}
