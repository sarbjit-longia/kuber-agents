import SwiftUI

struct PnLSummarySection: View {
    let pnl: [String: AnyCodable]?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("P&L Summary", systemImage: "chart.line.uptrend.xyaxis")
                .font(.headline)

            if let pnl, !pnl.isEmpty {
                VStack(spacing: 16) {
                    // Total P&L hero card
                    if let totalPnl = extractDouble("total_pnl") ?? extractDouble("total")
                        ?? extractDouble("net_pnl") {
                        totalPnLCard(totalPnl)
                    }

                    // Breakdown rows
                    VStack(spacing: 0) {
                        // Realized P&L
                        if let realized = extractDouble("realized_pnl") ?? extractDouble("realized") {
                            pnlRow(label: "Realized P&L", value: realized, icon: "checkmark.circle")
                            Divider().padding(.horizontal)
                        }

                        // Unrealized P&L
                        if let unrealized = extractDouble("unrealized_pnl")
                            ?? extractDouble("unrealized") {
                            pnlRow(label: "Unrealized P&L", value: unrealized, icon: "clock")
                            Divider().padding(.horizontal)
                        }

                        // Gross profit
                        if let grossProfit = extractDouble("gross_profit") {
                            pnlRow(label: "Gross Profit", value: grossProfit, icon: "arrow.up")
                            Divider().padding(.horizontal)
                        }

                        // Gross loss
                        if let grossLoss = extractDouble("gross_loss") {
                            pnlRow(label: "Gross Loss", value: grossLoss, icon: "arrow.down")
                            Divider().padding(.horizontal)
                        }

                        // Commission / Fees
                        if let fees = extractDouble("commission") ?? extractDouble("fees")
                            ?? extractDouble("total_fees") {
                            HStack {
                                Image(systemName: "banknote")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .frame(width: 20)
                                Text("Fees / Commission")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Text(fees.costFormatted)
                                    .font(.subheadline.weight(.medium))
                                    .foregroundStyle(.statusWarning)
                            }
                            .padding(.horizontal)
                            .padding(.vertical, 10)
                            Divider().padding(.horizontal)
                        }

                        // Return percentage
                        if let returnPct = extractDouble("return_pct") ?? extractDouble("return_percent")
                            ?? extractDouble("pnl_percent") {
                            HStack {
                                Image(systemName: "percent")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .frame(width: 20)
                                Text("Return")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                Spacer()
                                PnLText(value: returnPct, style: .percent)
                                    .font(.subheadline.weight(.semibold))
                            }
                            .padding(.horizontal)
                            .padding(.vertical, 10)
                        }
                    }
                    .cardStyle()

                    // Per-trade breakdown
                    if let trades = extractTrades() {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("By Trade")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(.secondary)

                            VStack(spacing: 0) {
                                ForEach(Array(trades.enumerated()), id: \.offset) { index, trade in
                                    tradeBreakdownRow(trade, index: index)
                                    if index < trades.count - 1 {
                                        Divider().padding(.horizontal)
                                    }
                                }
                            }
                            .cardStyle()
                        }
                    }
                }
            } else {
                noDataView
            }
        }
    }

    // MARK: - Total P&L Card

    @ViewBuilder
    private func totalPnLCard(_ value: Double) -> some View {
        VStack(spacing: 8) {
            Text("Total P&L")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            PnLText(value: value)
                .font(.system(size: 32, weight: .bold, design: .rounded))

            if let returnPct = extractDouble("return_pct") ?? extractDouble("return_percent") {
                PnLText(value: returnPct, style: .percent)
                    .font(.headline)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.pnlColor(for: value).opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .strokeBorder(Color.pnlColor(for: value).opacity(0.2), lineWidth: 1)
                )
        )
    }

    // MARK: - P&L Row

    @ViewBuilder
    private func pnlRow(label: String, value: Double, icon: String) -> some View {
        HStack {
            Image(systemName: icon)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 20)
            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Spacer()
            PnLText(value: value)
                .font(.subheadline.weight(.semibold))
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
    }

    // MARK: - Trade Breakdown

    @ViewBuilder
    private func tradeBreakdownRow(_ trade: [String: Any], index: Int) -> some View {
        let symbol = trade["symbol"] as? String ?? "Trade \(index + 1)"
        let pnlValue = (trade["pnl"] as? Double) ?? (trade["profit"] as? Double) ?? 0

        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(symbol)
                    .font(.subheadline.weight(.medium))
                if let side = trade["side"] as? String {
                    Text(side.uppercased())
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(
                            side.lowercased() == "buy" ? Color.actionBuy : Color.actionSell
                        )
                }
            }
            Spacer()
            PnLText(value: pnlValue)
                .font(.subheadline.weight(.semibold))
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
    }

    private var noDataView: some View {
        VStack(spacing: 8) {
            Image(systemName: "chart.line.uptrend.xyaxis")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No P&L data available")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .cardStyle()
    }

    // MARK: - Helpers

    private func extractDouble(_ key: String) -> Double? {
        if let val = pnl?[key]?.doubleValue { return val }
        if let val = pnl?[key]?.intValue { return Double(val) }
        return nil
    }

    private func extractTrades() -> [[String: Any]]? {
        guard let tradesValue = pnl?["trades"] ?? pnl?["by_trade"],
              let array = tradesValue.arrayValue else {
            return nil
        }
        let trades = array.compactMap { $0 as? [String: Any] }
        return trades.isEmpty ? nil : trades
    }
}

#Preview {
    ScrollView {
        PnLSummarySection(pnl: nil)
            .padding()
    }
    .background(Color.surfaceBackground)
    .preferredColorScheme(.dark)
}
