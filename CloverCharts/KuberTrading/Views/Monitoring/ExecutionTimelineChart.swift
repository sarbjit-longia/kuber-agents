import Charts
import SwiftUI

struct ExecutionTimelineChart: View {
    let executions: [ExecutionSummary]

    private var chartData: [ChartEntry] {
        // Group executions by date and status
        var grouped: [String: [String: Int]] = [:]

        for execution in executions {
            guard let startedAt = execution.startedAt else { continue }
            let dateStr = String(startedAt.prefix(10)) // YYYY-MM-DD
            let status = execution.status

            if grouped[dateStr] == nil {
                grouped[dateStr] = [:]
            }
            grouped[dateStr]?[status, default: 0] += 1
        }

        // Convert to chart entries
        var entries: [ChartEntry] = []
        for (date, statusCounts) in grouped {
            for (status, count) in statusCounts {
                entries.append(ChartEntry(date: date, status: status, count: count))
            }
        }

        return entries.sorted { $0.date < $1.date }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Execution Timeline")
                .font(.subheadline.weight(.semibold))

            if chartData.isEmpty {
                HStack {
                    Spacer()
                    Text("No execution data to display")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                .frame(height: 120)
            } else {
                Chart(chartData) { entry in
                    BarMark(
                        x: .value("Date", entry.date),
                        y: .value("Count", entry.count)
                    )
                    .foregroundStyle(Color.executionStatusColor(entry.status))
                    .cornerRadius(3)
                }
                .chartXAxis {
                    AxisMarks(values: .automatic(desiredCount: 5)) { value in
                        AxisValueLabel {
                            if let dateStr = value.as(String.self) {
                                Text(abbreviatedDate(dateStr))
                                    .font(.caption2)
                            }
                        }
                        AxisGridLine()
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .leading) { _ in
                        AxisValueLabel()
                            .font(.caption2)
                        AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [4]))
                    }
                }
                .chartLegend(position: .bottom, alignment: .leading, spacing: 8) {
                    HStack(spacing: 12) {
                        legendItem("Completed", .statusSuccess)
                        legendItem("Running", .brandPrimary)
                        legendItem("Monitoring", .statusWarning)
                        legendItem("Failed", .statusError)
                    }
                    .font(.caption2)
                }
                .frame(height: 160)
            }
        }
        .padding()
        .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 12))
    }

    private func legendItem(_ label: String, _ color: Color) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(color)
                .frame(width: 6, height: 6)
            Text(label)
                .foregroundStyle(.secondary)
        }
    }

    private func abbreviatedDate(_ dateStr: String) -> String {
        // Convert YYYY-MM-DD to shorter format
        guard let date = dateFormatter.date(from: dateStr) else { return dateStr }
        return shortFormatter.string(from: date)
    }

    private var dateFormatter: DateFormatter {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }

    private var shortFormatter: DateFormatter {
        let f = DateFormatter()
        f.dateFormat = "MMM d"
        return f
    }
}

// MARK: - Chart Entry

private struct ChartEntry: Identifiable {
    var id: String { "\(date)-\(status)" }
    let date: String
    let status: String
    let count: Int
}

#Preview {
    ExecutionTimelineChart(executions: [])
        .padding()
        .preferredColorScheme(.dark)
}
