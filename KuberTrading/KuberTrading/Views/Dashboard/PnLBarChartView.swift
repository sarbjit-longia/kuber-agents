import SwiftUI
import Charts

struct PnLBarChartView: View {
    let data: [PnLHistoryEntry]
    @Binding var selectedDays: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("P&L History")
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
                Text("No P&L data available")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 200)
            } else {
                Chart(data, id: \.date) { entry in
                    BarMark(
                        x: .value("Date", entry.date),
                        y: .value("P&L", entry.pnl)
                    )
                    .foregroundStyle(entry.pnl >= 0 ? Color.pnlPositive : Color.pnlNegative)
                    .cornerRadius(3)
                }
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let doubleValue = value.as(Double.self) {
                                Text(doubleValue.currencyFormatted)
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

#Preview {
    PnLBarChartView(
        data: [
            PnLHistoryEntry(date: "2026-02-20", pnl: 120.50),
            PnLHistoryEntry(date: "2026-02-21", pnl: -45.30),
            PnLHistoryEntry(date: "2026-02-22", pnl: 85.00),
            PnLHistoryEntry(date: "2026-02-23", pnl: 210.75),
            PnLHistoryEntry(date: "2026-02-24", pnl: -30.00),
            PnLHistoryEntry(date: "2026-02-25", pnl: 55.20),
            PnLHistoryEntry(date: "2026-02-26", pnl: 180.40),
        ],
        selectedDays: .constant(7)
    )
    .padding()
    .preferredColorScheme(.dark)
}
