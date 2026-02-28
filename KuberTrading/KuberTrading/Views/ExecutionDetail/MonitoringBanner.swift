import SwiftUI

struct MonitoringBanner: View {
    let execution: Execution
    let onClosePosition: () -> Void

    @State private var showCloseConfirm = false

    var body: some View {
        VStack(spacing: 14) {
            // Header
            HStack {
                Image(systemName: "eye.fill")
                    .font(.title3)
                    .foregroundStyle(.statusWarning)

                Text("Position Monitoring")
                    .font(.subheadline.weight(.semibold))

                Spacer()

                StatusBadge(status: "monitoring", size: .small)
            }

            // Position info
            if let positionInfo = extractPositionInfo() {
                VStack(spacing: 8) {
                    // Symbol + Side
                    HStack {
                        if let symbol = positionInfo.symbol {
                            Text(symbol)
                                .font(.headline.weight(.bold))
                                .foregroundStyle(.brandPrimary)
                        }

                        if let side = positionInfo.side {
                            Text(side.uppercased())
                                .font(.caption.weight(.bold))
                                .foregroundStyle(side.lowercased() == "buy" ? .actionBuy : .actionSell)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(
                                    (side.lowercased() == "buy" ? Color.actionBuy : Color.actionSell).opacity(0.12),
                                    in: Capsule()
                                )
                        }

                        Spacer()
                    }

                    // Price info
                    HStack(spacing: 16) {
                        if let entryPrice = positionInfo.entryPrice {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Entry")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                Text(entryPrice.currencyFormatted)
                                    .font(.caption.weight(.semibold))
                            }
                        }

                        if let currentPrice = positionInfo.currentPrice {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Current")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                Text(currentPrice.currencyFormatted)
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.brandPrimary)
                            }
                        }

                        if let quantity = positionInfo.quantity {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Qty")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                Text(String(format: "%.2f", quantity))
                                    .font(.caption.weight(.semibold))
                            }
                        }

                        Spacer()
                    }

                    // Unrealized P&L
                    if let pnl = positionInfo.unrealizedPnl {
                        HStack {
                            Text("Unrealized P&L")
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Spacer()

                            PnLText(value: pnl)
                                .font(.subheadline.weight(.bold))
                        }
                        .padding(8)
                        .background(
                            Color.pnlColor(for: pnl).opacity(0.06),
                            in: RoundedRectangle(cornerRadius: 6)
                        )
                    }
                }
                .padding(10)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
            }

            // Close Position Button
            Button {
                showCloseConfirm = true
            } label: {
                Label("Close Position", systemImage: "xmark.circle.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .tint(.statusError)
            .controlSize(.large)
            .alert("Close Position", isPresented: $showCloseConfirm) {
                Button("Cancel", role: .cancel) {}
                Button("Close Position", role: .destructive) {
                    onClosePosition()
                }
            } message: {
                Text("Are you sure you want to close this position? This will execute a market order to close.")
            }
        }
        .padding()
        .background(Color.statusWarning.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.statusWarning.opacity(0.3), lineWidth: 1)
        )
    }

    // MARK: - Position Info Extraction

    private struct PositionInfo {
        let symbol: String?
        let side: String?
        let entryPrice: Double?
        let currentPrice: Double?
        let quantity: Double?
        let unrealizedPnl: Double?
    }

    private func extractPositionInfo() -> PositionInfo? {
        let result = execution.result?.dictValue

        let symbol = execution.symbol ?? (result?["symbol"] as? String)
        let side = result?["side"] as? String ?? result?["strategy_action"] as? String
        let entryPrice = result?["entry_price"] as? Double
        let currentPrice = result?["current_price"] as? Double
        let quantity = result?["quantity"] as? Double
        let unrealizedPnl = result?["unrealized_pnl"] as? Double ?? result?["pnl"] as? Double

        // Return nil only if we have absolutely no data
        if symbol == nil && side == nil && entryPrice == nil && unrealizedPnl == nil {
            return nil
        }

        return PositionInfo(
            symbol: symbol,
            side: side,
            entryPrice: entryPrice,
            currentPrice: currentPrice,
            quantity: quantity,
            unrealizedPnl: unrealizedPnl
        )
    }
}

#Preview {
    Text("MonitoringBanner Preview")
        .preferredColorScheme(.dark)
}
