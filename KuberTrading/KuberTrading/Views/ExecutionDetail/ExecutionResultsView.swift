import SwiftUI

struct ExecutionResultsView: View {
    let execution: Execution

    var body: some View {
        VStack(spacing: 12) {
            // Cost Breakdown Card
            if let cost = execution.costBreakdown {
                costBreakdownCard(cost)
            }

            // Strategy Result Card
            if let result = execution.result?.dictValue, !result.isEmpty {
                strategyResultCard(result)
            }

            // Trade Info Card
            if let result = execution.result?.dictValue {
                tradeInfoCard(result)
            }

            // No results placeholder
            if execution.costBreakdown == nil && execution.result == nil {
                VStack(spacing: 12) {
                    Image(systemName: "doc.text")
                        .font(.title2)
                        .foregroundStyle(.secondary)

                    Text("No results available yet")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)

                    if execution.status == "running" || execution.status == "monitoring" {
                        Text("Results will appear when the execution completes.")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 40)
            }
        }
    }

    // MARK: - Cost Breakdown Card

    private func costBreakdownCard(_ cost: CostBreakdown) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Cost Breakdown", systemImage: "dollarsign.circle")
                .font(.subheadline.weight(.semibold))

            VStack(spacing: 6) {
                costRow("LLM Cost", cost.llmCost ?? 0)
                costRow("Agent Rental", cost.agentRentalCost ?? 0)
                costRow("API Calls", cost.apiCallCost ?? 0)

                Divider()

                HStack {
                    Text("Total Cost")
                        .font(.subheadline.weight(.semibold))

                    Spacer()

                    Text((cost.totalCost ?? 0).costFormatted)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.statusWarning)
                }
            }

            // Per-agent breakdown
            if let byAgent = cost.byAgent, !byAgent.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("By Agent")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)

                    ForEach(byAgent.sorted(by: { $0.key < $1.key }), id: \.key) { agentType, agentCost in
                        HStack {
                            Text(agentType.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Spacer()

                            Text(agentCost.costFormatted)
                                .font(.caption.weight(.semibold))
                        }
                    }
                }
                .padding(8)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 6))
            }
        }
        .padding()
        .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 12))
    }

    private func costRow(_ label: String, _ value: Double) -> some View {
        HStack {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)

            Spacer()

            Text(value.costFormatted)
                .font(.caption.weight(.medium))
        }
    }

    // MARK: - Strategy Result Card

    private func strategyResultCard(_ result: [String: Any]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Strategy Result", systemImage: "brain")
                .font(.subheadline.weight(.semibold))

            // Strategy action
            if let action = result["strategy_action"] as? String ?? result["action"] as? String {
                HStack {
                    Text("Action")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Spacer()

                    Text(action.uppercased())
                        .font(.caption.weight(.bold))
                        .foregroundStyle(actionColor(action))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(actionColor(action).opacity(0.12), in: Capsule())
                }
            }

            // Confidence
            if let confidence = result["confidence"] as? Double {
                HStack {
                    Text("Confidence")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Spacer()

                    HStack(spacing: 4) {
                        Text(String(format: "%.0f%%", confidence * 100))
                            .font(.caption.weight(.semibold))

                        confidenceBar(confidence)
                    }
                }
            }

            // Reasoning
            if let reasoning = result["reasoning"] as? String, !reasoning.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Reasoning")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)

                    Text(reasoning)
                        .font(.caption)
                        .foregroundStyle(.primary)
                        .lineLimit(8)
                }
                .padding(8)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 6))
            }

            // Additional result fields
            let knownKeys: Set<String> = [
                "strategy_action", "action", "confidence", "reasoning",
                "symbol", "side", "entry_price", "current_price", "quantity",
                "pnl", "unrealized_pnl", "stop_loss", "take_profit",
            ]

            let extraFields = result.filter { !knownKeys.contains($0.key) }
            if !extraFields.isEmpty {
                ForEach(extraFields.sorted(by: { $0.key < $1.key }), id: \.key) { key, value in
                    HStack(alignment: .top) {
                        Text(key.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        Spacer()

                        Text(formatValue(value))
                            .font(.caption)
                            .foregroundStyle(.primary)
                            .multilineTextAlignment(.trailing)
                            .lineLimit(3)
                    }
                }
            }
        }
        .padding()
        .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Trade Info Card

    @ViewBuilder
    private func tradeInfoCard(_ result: [String: Any]) -> some View {
        let hasTradeInfo = result["entry_price"] != nil
            || result["stop_loss"] != nil
            || result["take_profit"] != nil
            || result["pnl"] != nil

        if hasTradeInfo {
            VStack(alignment: .leading, spacing: 10) {
                Label("Trade Details", systemImage: "chart.line.uptrend.xyaxis")
                    .font(.subheadline.weight(.semibold))

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    if let entryPrice = result["entry_price"] as? Double {
                        tradeInfoItem("Entry Price", entryPrice.currencyFormatted, .primary)
                    }

                    if let currentPrice = result["current_price"] as? Double {
                        tradeInfoItem("Current Price", currentPrice.currencyFormatted, .brandPrimary)
                    }

                    if let stopLoss = result["stop_loss"] as? Double {
                        tradeInfoItem("Stop Loss", stopLoss.currencyFormatted, .statusError)
                    }

                    if let takeProfit = result["take_profit"] as? Double {
                        tradeInfoItem("Take Profit", takeProfit.currencyFormatted, .statusSuccess)
                    }

                    if let quantity = result["quantity"] as? Double {
                        tradeInfoItem("Quantity", String(format: "%.2f", quantity), .primary)
                    }

                    if let pnl = result["pnl"] as? Double {
                        tradeInfoItem("P&L", pnl.pnlFormatted, Color.pnlColor(for: pnl))
                    }
                }
            }
            .padding()
            .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 12))
        }
    }

    private func tradeInfoItem(_ label: String, _ value: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)

            Text(value)
                .font(.caption.weight(.semibold))
                .foregroundStyle(color)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(8)
        .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 6))
    }

    // MARK: - Confidence Bar

    private func confidenceBar(_ value: Double) -> some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color.surfaceElevated)
                    .frame(height: 4)

                Capsule()
                    .fill(confidenceColor(value))
                    .frame(width: geo.size.width * value, height: 4)
            }
        }
        .frame(width: 60, height: 4)
    }

    // MARK: - Helpers

    private func actionColor(_ action: String) -> Color {
        let lowered = action.lowercased()
        if lowered.contains("buy") || lowered.contains("long") { return .actionBuy }
        if lowered.contains("sell") || lowered.contains("short") { return .actionSell }
        if lowered.contains("hold") || lowered.contains("wait") { return .statusWarning }
        return .secondary
    }

    private func confidenceColor(_ value: Double) -> Color {
        if value >= 0.7 { return .statusSuccess }
        if value >= 0.4 { return .statusWarning }
        return .statusError
    }

    private func formatValue(_ value: Any) -> String {
        if let str = value as? String { return str }
        if let num = value as? Double { return String(format: "%.4f", num) }
        if let num = value as? Int { return "\(num)" }
        if let bool = value as? Bool { return bool ? "Yes" : "No" }
        if let arr = value as? [Any] { return "[\(arr.count) items]" }
        if let dict = value as? [String: Any] { return "{\(dict.count) fields}" }
        return String(describing: value)
    }
}

#Preview {
    Text("Preview")
        .preferredColorScheme(.dark)
}
