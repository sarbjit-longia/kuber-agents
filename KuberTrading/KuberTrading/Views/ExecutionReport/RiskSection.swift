import SwiftUI

struct RiskSection: View {
    let risk: [String: AnyCodable]?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Risk Assessment", systemImage: "shield")
                .font(.headline)

            if let risk, !risk.isEmpty {
                VStack(spacing: 0) {
                    // Risk level
                    if let level = extractString("risk_level") ?? extractString("level") {
                        riskRow(label: "Risk Level") {
                            riskLevelBadge(level)
                        }
                        Divider().padding(.horizontal)
                    }

                    // Max drawdown
                    if let drawdown = extractDouble("max_drawdown") ?? extractDouble("drawdown") {
                        riskRow(label: "Max Drawdown") {
                            Text(drawdown.percentFormatted)
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(.statusError)
                        }
                        Divider().padding(.horizontal)
                    }

                    // Position sizing
                    if let sizing = extractString("position_sizing") ?? extractString("position_size") {
                        riskRow(label: "Position Sizing") {
                            Text(sizing)
                                .font(.subheadline.weight(.medium))
                        }
                        Divider().padding(.horizontal)
                    } else if let sizingPct = extractDouble("position_size_pct") {
                        riskRow(label: "Position Size") {
                            Text(String(format: "%.1f%%", sizingPct))
                                .font(.subheadline.weight(.medium))
                        }
                        Divider().padding(.horizontal)
                    }

                    // Stop loss
                    if let stopLoss = extractDouble("stop_loss") ?? extractDouble("stop_loss_price") {
                        riskRow(label: "Stop Loss") {
                            Text(stopLoss.currencyFormatted)
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(.statusError)
                        }
                        Divider().padding(.horizontal)
                    } else if let stopLossPct = extractDouble("stop_loss_pct") {
                        riskRow(label: "Stop Loss") {
                            Text(String(format: "%.2f%%", stopLossPct))
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(.statusError)
                        }
                        Divider().padding(.horizontal)
                    }

                    // Take profit
                    if let takeProfit = extractDouble("take_profit") ?? extractDouble("take_profit_price") {
                        riskRow(label: "Take Profit") {
                            Text(takeProfit.currencyFormatted)
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(.statusSuccess)
                        }
                        Divider().padding(.horizontal)
                    }

                    // Risk/Reward ratio
                    if let ratio = extractDouble("risk_reward_ratio") ?? extractDouble("risk_reward") {
                        riskRow(label: "Risk/Reward") {
                            Text(String(format: "1:%.2f", ratio))
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(ratio >= 2.0 ? .statusSuccess : ratio >= 1.0 ? .statusWarning : .statusError)
                        }
                        Divider().padding(.horizontal)
                    }

                    // Max position value
                    if let maxValue = extractDouble("max_position_value") {
                        riskRow(label: "Max Position Value") {
                            Text(maxValue.currencyFormatted)
                                .font(.subheadline.weight(.medium))
                        }
                        Divider().padding(.horizontal)
                    }

                    // Risk notes
                    if let notes = extractString("notes") ?? extractString("risk_notes")
                        ?? extractString("assessment") {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Assessment")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                            Text(notes)
                                .font(.subheadline)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                .cardStyle()
            } else {
                noDataView
            }
        }
    }

    // MARK: - Risk Row

    @ViewBuilder
    private func riskRow(
        label: String,
        @ViewBuilder trailing: () -> some View
    ) -> some View {
        HStack {
            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Spacer()
            trailing()
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
    }

    // MARK: - Risk Level Badge

    @ViewBuilder
    private func riskLevelBadge(_ level: String) -> some View {
        let color = riskLevelColor(level)
        HStack(spacing: 4) {
            Circle()
                .fill(color)
                .frame(width: 8, height: 8)
            Text(level.capitalized)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(color)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
        .background(color.opacity(0.15), in: Capsule())
    }

    private func riskLevelColor(_ level: String) -> Color {
        switch level.lowercased() {
        case "low", "minimal":
            return .statusSuccess
        case "medium", "moderate":
            return .statusWarning
        case "high":
            return .orange
        case "very_high", "critical", "extreme":
            return .statusError
        default:
            return .secondary
        }
    }

    private var noDataView: some View {
        VStack(spacing: 8) {
            Image(systemName: "shield")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No risk data available")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .cardStyle()
    }

    // MARK: - Helpers

    private func extractString(_ key: String) -> String? {
        risk?[key]?.stringValue
    }

    private func extractDouble(_ key: String) -> Double? {
        if let val = risk?[key]?.doubleValue { return val }
        if let val = risk?[key]?.intValue { return Double(val) }
        return nil
    }
}

#Preview {
    ScrollView {
        RiskSection(risk: nil)
            .padding()
    }
    .background(Color.surfaceBackground)
    .preferredColorScheme(.dark)
}
