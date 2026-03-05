import SwiftUI

struct AIAnalysisSection: View {
    let analysis: [String: AnyCodable]?
    let tradeAnalysis: [String: AnyCodable]?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("AI Analysis", systemImage: "brain")
                .font(.headline)

            if hasContent {
                VStack(alignment: .leading, spacing: 16) {
                    // Rating badge
                    if let rating = extractString("rating", from: analysis)
                        ?? extractString("overall_rating", from: analysis) {
                        ratingBadge(rating)
                    }

                    // Main analysis text
                    if let text = analysisText {
                        MarkdownView(content: text)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    // Trade analysis section
                    if let tradeText = tradeAnalysisText {
                        Divider()

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Trade Analysis")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(.brandPrimary)

                            MarkdownView(content: tradeText)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }

                    // Key insights
                    if let insights = extractArray("key_insights", from: analysis)
                        ?? extractArray("insights", from: analysis) {
                        Divider()

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Key Insights")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(.brandPrimary)

                            ForEach(Array(insights.enumerated()), id: \.offset) { _, insight in
                                if let text = insight as? String {
                                    HStack(alignment: .top, spacing: 8) {
                                        Image(systemName: "lightbulb.fill")
                                            .font(.caption)
                                            .foregroundStyle(.statusWarning)
                                            .padding(.top, 2)
                                        Text(text)
                                            .font(.subheadline)
                                    }
                                }
                            }
                        }
                    }

                    // Recommendations
                    if let recommendations = extractArray("recommendations", from: analysis) {
                        Divider()

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Recommendations")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(.brandPrimary)

                            ForEach(Array(recommendations.enumerated()), id: \.offset) { _, rec in
                                if let text = rec as? String {
                                    HStack(alignment: .top, spacing: 8) {
                                        Image(systemName: "arrow.right.circle.fill")
                                            .font(.caption)
                                            .foregroundStyle(.statusInfo)
                                            .padding(.top, 2)
                                        Text(text)
                                            .font(.subheadline)
                                    }
                                }
                            }
                        }
                    }
                }
                .cardStyle()
            } else {
                noDataView
            }
        }
    }

    // MARK: - Rating Badge

    @ViewBuilder
    private func ratingBadge(_ rating: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: ratingIcon(for: rating))
                .foregroundStyle(ratingColor(for: rating))
            Text(rating.capitalized)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(ratingColor(for: rating))
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(ratingColor(for: rating).opacity(0.15), in: Capsule())
    }

    private func ratingIcon(for rating: String) -> String {
        switch rating.lowercased() {
        case "excellent", "strong_buy", "strong buy":
            return "star.fill"
        case "good", "buy":
            return "hand.thumbsup.fill"
        case "neutral", "hold":
            return "minus.circle.fill"
        case "poor", "sell":
            return "hand.thumbsdown.fill"
        case "bad", "strong_sell", "strong sell":
            return "exclamationmark.triangle.fill"
        default:
            return "circle.fill"
        }
    }

    private func ratingColor(for rating: String) -> Color {
        switch rating.lowercased() {
        case "excellent", "strong_buy", "strong buy":
            return .statusSuccess
        case "good", "buy":
            return .pnlPositive
        case "neutral", "hold":
            return .statusWarning
        case "poor", "sell":
            return .statusError.opacity(0.8)
        case "bad", "strong_sell", "strong sell":
            return .statusError
        default:
            return .secondary
        }
    }

    private var noDataView: some View {
        VStack(spacing: 8) {
            Image(systemName: "brain")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No AI analysis available")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .cardStyle()
    }

    // MARK: - Helpers

    private var hasContent: Bool {
        analysis != nil || tradeAnalysis != nil
    }

    private var analysisText: String? {
        extractString("analysis", from: analysis)
            ?? extractString("text", from: analysis)
            ?? extractString("content", from: analysis)
            ?? extractString("summary", from: analysis)
    }

    private var tradeAnalysisText: String? {
        extractString("analysis", from: tradeAnalysis)
            ?? extractString("text", from: tradeAnalysis)
            ?? extractString("content", from: tradeAnalysis)
            ?? extractString("summary", from: tradeAnalysis)
    }

    private func extractString(_ key: String, from dict: [String: AnyCodable]?) -> String? {
        dict?[key]?.stringValue
    }

    private func extractArray(_ key: String, from dict: [String: AnyCodable]?) -> [Any]? {
        dict?[key]?.arrayValue
    }
}

#Preview {
    ScrollView {
        AIAnalysisSection(
            analysis: nil,
            tradeAnalysis: nil
        )
        .padding()
    }
    .background(Color.surfaceBackground)
    .preferredColorScheme(.dark)
}
