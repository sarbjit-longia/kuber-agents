import SwiftUI

struct StatCardView: View {
    let title: String
    let value: String
    let icon: String
    var subtitle: String?
    var trend: Double?
    var tintColor: Color = .brandPrimary

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: icon)
                    .font(.title3)
                    .foregroundStyle(tintColor)

                Spacer()

                if let trend {
                    HStack(spacing: 2) {
                        Image(systemName: trend >= 0 ? "arrow.up.right" : "arrow.down.right")
                        Text(trend.percentFormatted)
                    }
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(Color.pnlColor(for: trend))
                }
            }

            Text(value)
                .font(.title2.weight(.bold))
                .lineLimit(1)
                .minimumScaleFactor(0.7)

            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)

            if let subtitle {
                Text(subtitle)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 12))
    }
}

#Preview {
    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
        StatCardView(title: "Active Pipelines", value: "5", icon: "arrow.triangle.branch", subtitle: "3 signal, 2 periodic", tintColor: .brandPrimary)
        StatCardView(title: "Total P&L", value: "+$1,234.56", icon: "chart.line.uptrend.xyaxis", trend: 12.5, tintColor: .statusSuccess)
        StatCardView(title: "Executions Today", value: "12", icon: "play.circle", subtitle: "8 completed, 2 running", tintColor: .statusInfo)
        StatCardView(title: "Total Cost", value: "$45.23", icon: "dollarsign.circle", tintColor: .statusWarning)
    }
    .padding()
    .preferredColorScheme(.dark)
}
