import SwiftUI

struct ExecutionRow: View {
    let execution: ExecutionSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Top row: pipeline name + status
            HStack {
                Text(execution.pipelineName ?? "Pipeline")
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)

                Spacer()

                StatusBadge(status: execution.status, size: .small)
            }

            // Middle row: symbol, mode, trigger, trade outcome
            HStack(spacing: 8) {
                if let symbol = execution.symbol, !symbol.isEmpty {
                    Text(symbol)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.brandPrimary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.brandPrimary.opacity(0.12), in: Capsule())
                }

                Text(execution.mode.capitalized)
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(execution.mode.lowercased() == "live" ? .accountLive : .accountPaper)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(
                        (execution.mode.lowercased() == "live" ? Color.accountLive : Color.accountPaper).opacity(0.12),
                        in: Capsule()
                    )

                if let triggerMode = execution.triggerMode {
                    Image(systemName: triggerMode == "signal" ? "antenna.radiowaves.left.and.right" : "clock.arrow.circlepath")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Trade outcome badge
                if let outcome = execution.tradeOutcome, !outcome.isEmpty {
                    tradeOutcomeBadge(outcome)
                }
            }

            // Bottom row: time, duration, cost/P&L
            HStack(spacing: 12) {
                // Start time
                if let startedAt = execution.startedAt {
                    Label(startedAt.formattedRelative, systemImage: "clock")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                // Duration
                if let durationSeconds = execution.durationSeconds {
                    Text(Int(durationSeconds).durationFormatted)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                } else if execution.status.lowercased() == "running" || execution.status.lowercased() == "monitoring" {
                    HStack(spacing: 2) {
                        ProgressView()
                            .scaleEffect(0.5)
                        Text("In progress")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                // P&L (only show for executed trades with non-zero P&L)
                if let pnlValue = extractPnL(), pnlValue != 0 {
                    PnLText(value: pnlValue)
                        .font(.caption.weight(.semibold))
                }

                // Cost (only show if > 0)
                if let cost = execution.totalCost, cost > 0 {
                    HStack(spacing: 2) {
                        Image(systemName: "dollarsign.circle")
                            .font(.caption2)
                        Text(cost.costFormatted)
                            .font(.caption2)
                    }
                    .foregroundStyle(.statusWarning)
                }
            }
        }
    }

    // MARK: - Trade Outcome Badge

    @ViewBuilder
    private func tradeOutcomeBadge(_ outcome: String) -> some View {
        let (label, color) = tradeOutcomeDisplay(outcome)
        Text(label)
            .font(.caption2.weight(.medium))
            .foregroundStyle(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.12), in: Capsule())
    }

    private func tradeOutcomeDisplay(_ outcome: String) -> (String, Color) {
        switch outcome.lowercased() {
        case "executed":
            return ("Executed", .statusSuccess)
        case "skipped":
            return ("Skipped", .secondary)
        case "rejected":
            return ("Rejected", .statusError)
        case "no_action", "no action":
            return ("No Action", .secondary)
        case "no_trade", "no trade":
            return ("No Trade", .statusWarning)
        case "pending":
            return ("Pending", .statusWarning)
        case "cancelled":
            return ("Cancelled", .secondary)
        default:
            return (outcome.capitalized, .secondary)
        }
    }

    // MARK: - P&L Extraction

    private func extractPnL() -> Double? {
        guard let result = execution.result?.dictValue else { return nil }

        // Try result.final_pnl first
        if let pnl = asDouble(result["final_pnl"]) { return pnl }

        // Try result.trade_outcome.pnl (only for actually executed trades)
        if let tradeOutcome = result["trade_outcome"] as? [String: Any] {
            let status = tradeOutcome["status"] as? String ?? ""
            if status.lowercased() == "executed",
               let pnl = asDouble(tradeOutcome["pnl"]) { return pnl }
        }

        return nil
    }

    private func asDouble(_ value: Any?) -> Double? {
        if let d = value as? Double { return d }
        if let i = value as? Int { return Double(i) }
        if let n = value as? NSNumber { return n.doubleValue }
        return nil
    }
}
