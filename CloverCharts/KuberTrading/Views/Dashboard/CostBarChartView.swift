import SwiftUI
import Charts

struct CostBarChartView: View {
    let data: [CostHistoryEntry]
    @Binding var selectedDays: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Cost History")
                    .font(.headline)

                Spacer()

                Picker("Days", selection: $selectedDays) {
                    Text("7D").tag(7)
                    Text("14D").tag(14)
                    Text("30D").tag(30)
                }
                .pickerStyle(.segmented)
                .frame(width: 160)
            }

            if data.isEmpty {
                Text("No cost data available")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 200)
            } else {
                Chart(data, id: \.date) { entry in
                    BarMark(
                        x: .value("Date", entry.date),
                        y: .value("Cost", entry.cost)
                    )
                    .foregroundStyle(Color.brandPrimary.gradient)
                    .cornerRadius(3)
                }
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let doubleValue = value.as(Double.self) {
                                Text(doubleValue.costFormatted)
                                    .font(.caption2)
                            }
                        }
                    }
                }
                .chartXAxis {
                    AxisMarks(values: .automatic(desiredCount: min(data.count, 7))) { value in
                        AxisValueLabel {
                            if let dateStr = value.as(String.self) {
                                Text(shortDateLabel(dateStr))
                                    .font(.caption2)
                            }
                        }
                    }
                }
                .frame(height: 200)
            }
        }
        .cardStyle()
    }

    private func shortDateLabel(_ dateStr: String) -> String {
        let parts = dateStr.split(separator: "-")
        guard parts.count >= 3 else { return dateStr }
        return "\(parts[1])/\(parts[2])"
    }
}
