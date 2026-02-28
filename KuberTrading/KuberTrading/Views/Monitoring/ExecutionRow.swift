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

            // Middle row: symbol, mode, trigger
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
                    .foregroundStyle(execution.mode == "live" ? .accountLive : .accountPaper)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(
                        (execution.mode == "live" ? Color.accountLive : Color.accountPaper).opacity(0.12),
                        in: Capsule()
                    )

                if let triggerMode = execution.triggerMode {
                    Image(systemName: triggerMode == "signal" ? "antenna.radiowaves.left.and.right" : "clock.arrow.circlepath")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Spacer()
            }

            // Bottom row: time, duration, cost, P&L
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
                } else if execution.status == "running" || execution.status == "monitoring" {
                    HStack(spacing: 2) {
                        ProgressView()
                            .scaleEffect(0.5)
                        Text("In progress")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                // Cost
                if let cost = execution.totalCost {
                    Text(cost.costFormatted)
                        .font(.caption2)
                        .foregroundStyle(.statusWarning)
                }

                // P&L
                if let result = execution.result?.dictValue,
                   let pnlValue = result["pnl"] as? Double {
                    PnLText(value: pnlValue, style: .compact)
                        .font(.caption2.weight(.semibold))
                }
            }
        }
    }
}
