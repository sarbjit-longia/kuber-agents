import SwiftUI

struct ApprovalBanner: View {
    let execution: Execution
    let timeRemaining: TimeInterval
    let onApprove: () -> Void
    let onReject: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            // Header with countdown
            HStack {
                Image(systemName: "exclamationmark.shield.fill")
                    .font(.title3)
                    .foregroundStyle(.orange)

                Text("Approval Required")
                    .font(.subheadline.weight(.semibold))

                Spacer()

                // Countdown timer
                VStack(alignment: .trailing, spacing: 2) {
                    Text(formattedCountdown)
                        .font(.callout.weight(.bold).monospacedDigit())
                        .foregroundStyle(countdownColor)

                    Text("remaining")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            // Trade Details Summary
            if let tradeDetails = extractTradeDetails() {
                VStack(spacing: 8) {
                    ForEach(tradeDetails, id: \.label) { detail in
                        HStack {
                            Text(detail.label)
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Spacer()

                            Text(detail.value)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(detail.color)
                        }
                    }
                }
                .padding(10)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
            }

            // Expires at
            if let expiresAt = execution.approvalExpiresAt {
                HStack {
                    Image(systemName: "clock")
                        .font(.caption)

                    Text("Expires: \(expiresAt.formattedDateTime)")
                        .font(.caption)
                }
                .foregroundStyle(.secondary)
            }

            // Action Buttons
            HStack(spacing: 12) {
                Button {
                    onReject()
                } label: {
                    Label("Reject", systemImage: "xmark")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .tint(.statusError)
                .controlSize(.large)

                Button {
                    onApprove()
                } label: {
                    Label("Approve", systemImage: "checkmark")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(.statusSuccess)
                .controlSize(.large)
            }
        }
        .padding()
        .background(Color.orange.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.orange.opacity(0.3), lineWidth: 1)
        )
    }

    // MARK: - Countdown

    private var formattedCountdown: String {
        if timeRemaining <= 0 {
            return "Expired"
        }
        let minutes = Int(timeRemaining) / 60
        let seconds = Int(timeRemaining) % 60
        if minutes > 0 {
            return String(format: "%d:%02d", minutes, seconds)
        }
        return String(format: "0:%02d", seconds)
    }

    private var countdownColor: Color {
        if timeRemaining <= 0 { return .statusError }
        if timeRemaining < 60 { return .statusError }
        if timeRemaining < 180 { return .statusWarning }
        return .orange
    }

    // MARK: - Trade Details Extraction

    private struct TradeDetail {
        let label: String
        let value: String
        let color: Color
    }

    private func extractTradeDetails() -> [TradeDetail]? {
        guard let result = execution.result?.dictValue else { return nil }

        var details: [TradeDetail] = []

        // Symbol
        if let symbol = execution.symbol ?? (result["symbol"] as? String) {
            details.append(TradeDetail(label: "Symbol", value: symbol, color: .brandPrimary))
        }

        // Action
        if let action = result["strategy_action"] as? String ?? result["action"] as? String {
            let actionColor: Color = action.lowercased().contains("buy") ? .actionBuy : .actionSell
            details.append(TradeDetail(label: "Action", value: action.capitalized, color: actionColor))
        }

        // Mode
        details.append(TradeDetail(
            label: "Mode",
            value: execution.mode.capitalized,
            color: execution.mode == "live" ? .accountLive : .accountPaper
        ))

        // Quantity
        if let quantity = result["quantity"] as? Double {
            details.append(TradeDetail(label: "Quantity", value: String(format: "%.2f", quantity), color: .primary))
        }

        // Price
        if let price = result["entry_price"] as? Double ?? result["price"] as? Double {
            details.append(TradeDetail(label: "Price", value: price.currencyFormatted, color: .primary))
        }

        return details.isEmpty ? nil : details
    }
}

#Preview {
    Text("ApprovalBanner Preview")
        .preferredColorScheme(.dark)
    .padding()
    .preferredColorScheme(.dark)
}
