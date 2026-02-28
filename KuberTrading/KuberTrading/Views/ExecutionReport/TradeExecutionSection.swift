import SwiftUI

struct TradeExecutionSection: View {
    let trade: [String: AnyCodable]?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Trade Execution", systemImage: "arrow.left.arrow.right")
                .font(.headline)

            if let trade, !trade.isEmpty {
                VStack(spacing: 0) {
                    // Side (Buy/Sell)
                    if let side = extractString("side") ?? extractString("action") {
                        tradeRow(label: "Side") {
                            sideBadge(side)
                        }
                        Divider().padding(.horizontal)
                    }

                    // Entry price
                    if let entryPrice = extractDouble("entry_price") ?? extractDouble("fill_price") {
                        tradeRow(label: "Entry Price") {
                            Text(entryPrice.currencyFormatted)
                                .font(.subheadline.weight(.semibold))
                        }
                        Divider().padding(.horizontal)
                    }

                    // Exit price
                    if let exitPrice = extractDouble("exit_price") ?? extractDouble("close_price") {
                        tradeRow(label: "Exit Price") {
                            Text(exitPrice.currencyFormatted)
                                .font(.subheadline.weight(.semibold))
                        }
                        Divider().padding(.horizontal)
                    }

                    // Quantity
                    if let quantity = extractDouble("quantity") ?? extractDouble("qty")
                        ?? extractDouble("shares") {
                        tradeRow(label: "Quantity") {
                            Text(formatQuantity(quantity))
                                .font(.subheadline.weight(.medium))
                        }
                        Divider().padding(.horizontal)
                    }

                    // Order type
                    if let orderType = extractString("order_type") ?? extractString("type") {
                        tradeRow(label: "Order Type") {
                            Text(orderType.capitalized)
                                .font(.subheadline.weight(.medium))
                        }
                        Divider().padding(.horizontal)
                    }

                    // Fill status
                    if let status = extractString("fill_status") ?? extractString("order_status") {
                        tradeRow(label: "Fill Status") {
                            StatusBadge(status: status, size: .small)
                        }
                        Divider().padding(.horizontal)
                    }

                    // Slippage
                    if let slippage = extractDouble("slippage") ?? extractDouble("slippage_pct") {
                        tradeRow(label: "Slippage") {
                            Text(String(format: "%.4f%%", slippage))
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(abs(slippage) > 0.1 ? .statusWarning : .secondary)
                        }
                        Divider().padding(.horizontal)
                    }

                    // Commission
                    if let commission = extractDouble("commission") ?? extractDouble("fee") {
                        tradeRow(label: "Commission") {
                            Text(commission.costFormatted)
                                .font(.subheadline.weight(.medium))
                        }
                        Divider().padding(.horizontal)
                    }

                    // Broker
                    if let broker = extractString("broker") ?? extractString("broker_name") {
                        tradeRow(label: "Broker") {
                            Text(broker.capitalized)
                                .font(.subheadline.weight(.medium))
                        }
                        Divider().padding(.horizontal)
                    }

                    // Order ID
                    if let orderId = extractString("order_id") ?? extractString("broker_order_id") {
                        tradeRow(label: "Order ID") {
                            Text(orderId)
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }

                    // Filled at
                    if let filledAt = extractString("filled_at") ?? extractString("executed_at") {
                        Divider().padding(.horizontal)
                        tradeRow(label: "Executed At") {
                            Text(filledAt.formattedDateTime)
                                .font(.subheadline)
                        }
                    }
                }
                .cardStyle()
            } else {
                noDataView
            }
        }
    }

    // MARK: - Side Badge

    @ViewBuilder
    private func sideBadge(_ side: String) -> some View {
        let isBuy = ["buy", "long"].contains(side.lowercased())
        HStack(spacing: 4) {
            Image(systemName: isBuy ? "arrow.up.right" : "arrow.down.right")
                .font(.caption)
            Text(side.uppercased())
                .font(.caption.weight(.bold))
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
        .background(
            isBuy ? Color.actionBuy.opacity(0.2) : Color.actionSell.opacity(0.2),
            in: Capsule()
        )
        .foregroundStyle(isBuy ? .actionBuy : .actionSell)
    }

    // MARK: - Trade Row

    @ViewBuilder
    private func tradeRow(
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

    private var noDataView: some View {
        VStack(spacing: 8) {
            Image(systemName: "arrow.left.arrow.right")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No trade execution data")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text("This execution may not have placed a trade.")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .cardStyle()
    }

    // MARK: - Helpers

    private func formatQuantity(_ qty: Double) -> String {
        if qty == qty.rounded() {
            return String(format: "%.0f", qty)
        }
        return String(format: "%.4f", qty)
    }

    private func extractString(_ key: String) -> String? {
        trade?[key]?.stringValue
    }

    private func extractDouble(_ key: String) -> Double? {
        if let val = trade?[key]?.doubleValue { return val }
        if let val = trade?[key]?.intValue { return Double(val) }
        return nil
    }
}

#Preview {
    ScrollView {
        TradeExecutionSection(trade: nil)
            .padding()
    }
    .background(Color.surfaceBackground)
    .preferredColorScheme(.dark)
}
