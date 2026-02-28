import Foundation

extension Date {
    private static let isoFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let isoFormatterNoFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    private static let relativeFormatter: RelativeDateTimeFormatter = {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter
    }()

    private static let timeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return formatter
    }()

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, yyyy"
        return formatter
    }()

    private static let dateTimeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, yyyy 'at' HH:mm"
        return formatter
    }()

    static func fromISO(_ string: String) -> Date? {
        isoFormatter.date(from: string) ?? isoFormatterNoFractional.date(from: string)
    }

    var relativeString: String {
        Date.relativeFormatter.localizedString(for: self, relativeTo: .now)
    }

    var timeString: String {
        Date.timeFormatter.string(from: self)
    }

    var dateString: String {
        Date.dateFormatter.string(from: self)
    }

    var dateTimeString: String {
        Date.dateTimeFormatter.string(from: self)
    }
}

extension String {
    var asDate: Date? {
        Date.fromISO(self)
    }

    var formattedDate: String {
        asDate?.dateString ?? self
    }

    var formattedDateTime: String {
        asDate?.dateTimeString ?? self
    }

    var formattedRelative: String {
        asDate?.relativeString ?? self
    }
}
