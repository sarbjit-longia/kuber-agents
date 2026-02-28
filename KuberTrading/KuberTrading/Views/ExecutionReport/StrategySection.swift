import SwiftUI

struct StrategySection: View {
    let strategy: [String: AnyCodable]?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Strategy Details", systemImage: "lightbulb")
                .font(.headline)

            if let strategy, !strategy.isEmpty {
                VStack(spacing: 0) {
                    // Action taken
                    if let action = extractString("action") ?? extractString("strategy_action") {
                        strategyRow(label: "Action", icon: "arrow.up.arrow.down") {
                            actionBadge(action)
                        }
                        Divider().padding(.horizontal)
                    }

                    // Confidence level
                    if let confidence = extractDouble("confidence")
                        ?? extractDouble("confidence_level") {
                        strategyRow(label: "Confidence", icon: "gauge") {
                            confidenceView(confidence)
                        }
                        Divider().padding(.horizontal)
                    }

                    // Timeframe
                    if let timeframe = extractString("timeframe") ?? extractString("time_frame") {
                        strategyRow(label: "Timeframe") {
                            Text(timeframe)
                                .font(.subheadline.weight(.medium))
                        }
                        Divider().padding(.horizontal)
                    }

                    // Entry reason / Reasoning
                    if let reasoning = extractString("reasoning") ?? extractString("reason")
                        ?? extractString("entry_reason") {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Reasoning")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                            Text(reasoning)
                                .font(.subheadline)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                        Divider().padding(.horizontal)
                    }

                    // Indicators used
                    if let indicators = extractIndicators() {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Indicators Used")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)

                            FlowLayout(spacing: 6) {
                                ForEach(indicators, id: \.self) { indicator in
                                    Text(indicator)
                                        .font(.caption.weight(.medium))
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 4)
                                        .background(Color.brandPrimary.opacity(0.15), in: Capsule())
                                        .foregroundStyle(.brandPrimary)
                                }
                            }
                        }
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    // Additional notes
                    if let notes = extractString("notes") ?? extractString("additional_notes") {
                        Divider().padding(.horizontal)
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Notes")
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

    // MARK: - Action Badge

    @ViewBuilder
    private func actionBadge(_ action: String) -> some View {
        let isLong = ["buy", "long"].contains(action.lowercased())
        let isShort = ["sell", "short"].contains(action.lowercased())

        Text(action.uppercased())
            .font(.caption.weight(.bold))
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(
                isLong ? Color.actionBuy.opacity(0.2) :
                isShort ? Color.actionSell.opacity(0.2) :
                Color.surfaceElevated,
                in: Capsule()
            )
            .foregroundStyle(
                isLong ? .actionBuy :
                isShort ? .actionSell :
                .primary
            )
    }

    // MARK: - Confidence View

    @ViewBuilder
    private func confidenceView(_ confidence: Double) -> some View {
        let normalized = confidence > 1.0 ? confidence / 100.0 : confidence
        HStack(spacing: 8) {
            ProgressView(value: normalized)
                .tint(confidenceColor(normalized))
                .frame(width: 80)
            Text(String(format: "%.0f%%", normalized * 100))
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(confidenceColor(normalized))
        }
    }

    private func confidenceColor(_ value: Double) -> Color {
        if value >= 0.7 { return .statusSuccess }
        if value >= 0.4 { return .statusWarning }
        return .statusError
    }

    // MARK: - Strategy Row

    @ViewBuilder
    private func strategyRow(
        label: String,
        icon: String? = nil,
        @ViewBuilder trailing: () -> some View
    ) -> some View {
        HStack {
            if let icon {
                Image(systemName: icon)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(width: 20)
            }
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
            Image(systemName: "lightbulb")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No strategy details available")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .cardStyle()
    }

    // MARK: - Helpers

    private func extractString(_ key: String) -> String? {
        strategy?[key]?.stringValue
    }

    private func extractDouble(_ key: String) -> Double? {
        if let val = strategy?[key]?.doubleValue { return val }
        if let val = strategy?[key]?.intValue { return Double(val) }
        return nil
    }

    private func extractIndicators() -> [String]? {
        if let array = strategy?["indicators"]?.arrayValue ?? strategy?["indicators_used"]?.arrayValue {
            let strings = array.compactMap { $0 as? String }
            return strings.isEmpty ? nil : strings
        }
        return nil
    }
}

// MARK: - Flow Layout for Tags

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = FlowResult(in: proposal.replacingUnspecifiedDimensions().width, subviews: subviews, spacing: spacing)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = FlowResult(in: bounds.width, subviews: subviews, spacing: spacing)
        for (index, subview) in subviews.enumerated() {
            subview.place(at: CGPoint(x: bounds.minX + result.positions[index].x,
                                      y: bounds.minY + result.positions[index].y),
                          proposal: .unspecified)
        }
    }

    struct FlowResult {
        var positions: [CGPoint] = []
        var size: CGSize = .zero

        init(in maxWidth: CGFloat, subviews: Subviews, spacing: CGFloat) {
            var x: CGFloat = 0
            var y: CGFloat = 0
            var maxHeight: CGFloat = 0
            var rowMaxY: CGFloat = 0

            for subview in subviews {
                let size = subview.sizeThatFits(.unspecified)
                if x + size.width > maxWidth, x > 0 {
                    x = 0
                    y = rowMaxY + spacing
                }
                positions.append(CGPoint(x: x, y: y))
                maxHeight = max(maxHeight, size.height)
                rowMaxY = max(rowMaxY, y + size.height)
                x += size.width + spacing
                self.size.width = max(self.size.width, x)
            }
            self.size.height = rowMaxY
        }
    }
}

#Preview {
    ScrollView {
        StrategySection(strategy: nil)
            .padding()
    }
    .background(Color.surfaceBackground)
    .preferredColorScheme(.dark)
}
