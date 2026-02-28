import SwiftUI

extension Color {
    // MARK: - Brand Colors
    static let brandPrimary = Color(red: 0.25, green: 0.47, blue: 1.0)  // #3F78FF
    static let brandSecondary = Color(red: 0.56, green: 0.33, blue: 0.97)  // #8F54F8

    // MARK: - Surface Colors (Dark Theme)
    static let surfaceBackground = Color(red: 0.07, green: 0.07, blue: 0.09)  // #121217
    static let surfaceCard = Color(red: 0.11, green: 0.11, blue: 0.14)  // #1C1C24
    static let surfaceElevated = Color(red: 0.15, green: 0.15, blue: 0.19)  // #26262F

    // MARK: - Status Colors
    static let statusSuccess = Color(red: 0.18, green: 0.80, blue: 0.44)  // #2ECC71
    static let statusWarning = Color(red: 1.0, green: 0.76, blue: 0.03)  // #FFC107
    static let statusError = Color(red: 0.91, green: 0.30, blue: 0.24)  // #E74C3C
    static let statusInfo = Color(red: 0.20, green: 0.60, blue: 1.0)  // #3399FF

    // MARK: - P&L Colors
    static let pnlPositive = Color(red: 0.18, green: 0.80, blue: 0.44)  // Green
    static let pnlNegative = Color(red: 0.91, green: 0.30, blue: 0.24)  // Red
    static let pnlNeutral = Color.secondary

    // MARK: - Execution Status Colors
    static func executionStatusColor(_ status: String) -> Color {
        switch status.lowercased() {
        case "completed": return .statusSuccess
        case "running": return .brandPrimary
        case "monitoring": return .statusWarning
        case "failed", "communication_error": return .statusError
        case "pending": return .secondary
        case "cancelled": return .secondary
        case "paused": return .statusWarning
        case "awaiting_approval": return .orange
        case "needs_reconciliation": return .statusWarning
        default: return .secondary
        }
    }

    // MARK: - Trade Action Colors
    static let actionBuy = Color(red: 0.18, green: 0.80, blue: 0.44)
    static let actionSell = Color(red: 0.91, green: 0.30, blue: 0.24)

    // MARK: - Account Type Colors
    static let accountPaper = Color(red: 0.56, green: 0.33, blue: 0.97)
    static let accountLive = Color(red: 0.18, green: 0.80, blue: 0.44)
}

extension Color {
    static func pnlColor(for value: Double) -> Color {
        if value > 0 { return .pnlPositive }
        if value < 0 { return .pnlNegative }
        return .pnlNeutral
    }
}

// MARK: - ShapeStyle conformance for .foregroundStyle() shorthand

extension ShapeStyle where Self == Color {
    // Brand
    static var brandPrimary: Color { Color.brandPrimary }
    static var brandSecondary: Color { Color.brandSecondary }

    // Surface
    static var surfaceBackground: Color { Color.surfaceBackground }
    static var surfaceCard: Color { Color.surfaceCard }
    static var surfaceElevated: Color { Color.surfaceElevated }

    // Status
    static var statusSuccess: Color { Color.statusSuccess }
    static var statusWarning: Color { Color.statusWarning }
    static var statusError: Color { Color.statusError }
    static var statusInfo: Color { Color.statusInfo }

    // P&L
    static var pnlPositive: Color { Color.pnlPositive }
    static var pnlNegative: Color { Color.pnlNegative }
    static var pnlNeutral: Color { Color.pnlNeutral }

    // Trade Actions
    static var actionBuy: Color { Color.actionBuy }
    static var actionSell: Color { Color.actionSell }

    // Account Types
    static var accountPaper: Color { Color.accountPaper }
    static var accountLive: Color { Color.accountLive }
}
