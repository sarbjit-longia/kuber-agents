import SwiftUI

struct RecentExecutionRow: View {
    let execution: RecentExecution
    var onTap: (() -> Void)?

    var body: some View {
        Button {
            onTap?()
        } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(execution.pipelineName)
                            .font(.subheadline.weight(.medium))
                            .lineLimit(1)

                        if let action = execution.strategyAction {
                            Text(action)
                                .font(.caption2.weight(.bold))
                                .foregroundStyle(action.uppercased() == "BUY" ? Color.actionBuy : Color.actionSell)
                        }
                    }

                    HStack(spacing: 8) {
                        if let symbol = execution.symbol {
                            Text(symbol)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        Text(execution.mode.capitalized)
                            .font(.caption2)
                            .foregroundStyle(execution.mode == "live" ? Color.accountLive : Color.accountPaper)

                        if let startedAt = execution.startedAt {
                            Text(startedAt.formattedRelative)
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                    }
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    StatusBadge(status: execution.status, size: .small)

                    HStack(spacing: 8) {
                        if let pnl = execution.pnl, let value = pnl.value {
                            PnLText(value: value)
                                .font(.caption)
                        }

                        Text((execution.cost ?? 0).costFormatted)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding(.vertical, 6)
        }
        .buttonStyle(.plain)
    }
}
