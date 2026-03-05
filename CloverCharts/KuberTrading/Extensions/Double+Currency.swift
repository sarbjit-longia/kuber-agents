import Foundation

extension Double {
    var currencyFormatted: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = "USD"
        formatter.maximumFractionDigits = 2
        return formatter.string(from: NSNumber(value: self)) ?? "$\(self)"
    }

    var costFormatted: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = "USD"
        formatter.maximumFractionDigits = 4
        return formatter.string(from: NSNumber(value: self)) ?? "$\(self)"
    }

    var pnlFormatted: String {
        let sign = self >= 0 ? "+" : ""
        return "\(sign)\(currencyFormatted)"
    }

    var percentFormatted: String {
        let sign = self >= 0 ? "+" : ""
        return String(format: "\(sign)%.2f%%", self)
    }

    var compactFormatted: String {
        let absValue = abs(self)
        let sign = self < 0 ? "-" : ""
        if absValue >= 1_000_000 {
            return "\(sign)\(String(format: "%.1fM", absValue / 1_000_000))"
        } else if absValue >= 1_000 {
            return "\(sign)\(String(format: "%.1fK", absValue / 1_000))"
        }
        return String(format: "\(sign)%.2f", absValue)
    }
}

extension Int {
    var durationFormatted: String {
        if self < 60 {
            return "\(self)s"
        } else if self < 3600 {
            return "\(self / 60)m \(self % 60)s"
        } else {
            let hours = self / 3600
            let minutes = (self % 3600) / 60
            return "\(hours)h \(minutes)m"
        }
    }
}
