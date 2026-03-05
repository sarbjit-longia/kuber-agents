import SwiftUI
import Charts

struct PipelinePnLChartView: View {
    let pipelines: [DashboardPipeline]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Pipeline P&L")
                .font(.headline)

            if sortedPipelines.isEmpty {
                Text("No pipeline data available")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 160)
            } else {
                Chart(sortedPipelines, id: \.id) { pipeline in
                    BarMark(
                        x: .value("P&L", pipeline.totalPnl ?? 0),
                        y: .value("Pipeline", pipeline.name)
                    )
                    .foregroundStyle((pipeline.totalPnl ?? 0) >= 0 ? Color.pnlPositive : Color.pnlNegative)
                    .cornerRadius(4)
                    .annotation(position: (pipeline.totalPnl ?? 0) >= 0 ? .trailing : .leading) {
                        Text((pipeline.totalPnl ?? 0).pnlFormatted)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                .chartXAxis {
                    AxisMarks { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let doubleValue = value.as(Double.self) {
                                Text(doubleValue.currencyFormatted)
                                    .font(.caption2)
                            }
                        }
                    }
                }
                .chartYAxis {
                    AxisMarks { value in
                        AxisValueLabel {
                            if let name = value.as(String.self) {
                                Text(name.truncated(to: 15))
                                    .font(.caption2)
                            }
                        }
                    }
                }
                .frame(height: CGFloat(max(sortedPipelines.count * 40, 120)))
            }
        }
        .cardStyle()
    }

    private var sortedPipelines: [DashboardPipeline] {
        pipelines
            .filter { ($0.totalPnl ?? 0) != 0 }
            .sorted { abs($0.totalPnl ?? 0) > abs($1.totalPnl ?? 0) }
            .prefix(8)
            .map { $0 }
    }
}
