import SwiftUI
import Charts

struct ExecutionTimelineSection: View {
    let timeline: [[String: AnyCodable]]?
    let agentStates: [AgentState]?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Execution Timeline", systemImage: "clock")
                .font(.headline)

            if let entries = timelineEntries, !entries.isEmpty {
                VStack(alignment: .leading, spacing: 16) {
                    // Gantt-style chart
                    ganttChart(entries)

                    // Timeline list
                    VStack(spacing: 0) {
                        ForEach(Array(entries.enumerated()), id: \.offset) { index, entry in
                            timelineRow(entry, isLast: index == entries.count - 1)
                        }
                    }
                    .cardStyle()
                }
            } else {
                noDataView
            }
        }
    }

    // MARK: - Gantt Chart

    @ViewBuilder
    private func ganttChart(_ entries: [TimelineEntry]) -> some View {
        let minStart = entries.compactMap(\.startDate).min() ?? Date()

        Chart(entries) { entry in
            if let start = entry.startDate {
                let startOffset = start.timeIntervalSince(minStart)
                let duration = max(entry.durationSeconds, 0.5) // minimum bar width

                BarMark(
                    xStart: .value("Start", startOffset),
                    xEnd: .value("End", startOffset + duration),
                    y: .value("Agent", entry.displayName)
                )
                .foregroundStyle(barColor(for: entry.status))
                .clipShape(RoundedRectangle(cornerRadius: 4))
            }
        }
        .chartXAxis {
            AxisMarks(position: .bottom) { value in
                if let seconds = value.as(Double.self) {
                    AxisValueLabel {
                        Text(formatDuration(seconds))
                            .font(.caption2)
                    }
                    AxisGridLine()
                }
            }
        }
        .chartYAxis {
            AxisMarks { value in
                AxisValueLabel {
                    if let name = value.as(String.self) {
                        Text(name)
                            .font(.caption2)
                            .lineLimit(1)
                    }
                }
            }
        }
        .frame(height: max(CGFloat(entries.count) * 36, 120))
        .cardStyle()
    }

    // MARK: - Timeline Row

    @ViewBuilder
    private func timelineRow(_ entry: TimelineEntry, isLast: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            // Timeline dot and line
            VStack(spacing: 0) {
                Circle()
                    .fill(barColor(for: entry.status))
                    .frame(width: 10, height: 10)
                    .padding(.top, 4)

                if !isLast {
                    Rectangle()
                        .fill(Color.surfaceElevated)
                        .frame(width: 2)
                        .frame(maxHeight: .infinity)
                }
            }
            .frame(width: 10)

            // Content
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(entry.displayName)
                        .font(.subheadline.weight(.medium))
                    Spacer()
                    StatusBadge(status: entry.status, size: .small)
                }

                HStack(spacing: 12) {
                    if let start = entry.startDate {
                        Label(start.timeString, systemImage: "play.fill")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }

                    if let end = entry.endDate {
                        Label(end.timeString, systemImage: "stop.fill")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }

                    if entry.durationSeconds > 0 {
                        Label(
                            Int(entry.durationSeconds).durationFormatted,
                            systemImage: "timer"
                        )
                        .font(.caption2)
                        .foregroundStyle(.brandPrimary)
                    }
                }

                if let error = entry.errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.statusError)
                        .lineLimit(2)
                }
            }
            .padding(.bottom, isLast ? 0 : 12)
        }
        .padding(.horizontal)
        .padding(.vertical, 4)
    }

    private func barColor(for status: String) -> Color {
        Color.executionStatusColor(status)
    }

    private var noDataView: some View {
        VStack(spacing: 8) {
            Image(systemName: "clock")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No timeline data available")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .cardStyle()
    }

    // MARK: - Build Timeline Entries

    private var timelineEntries: [TimelineEntry]? {
        var entries: [TimelineEntry] = []

        // Prefer executive report timeline data
        if let timeline {
            for dict in timeline {
                let name = dict["agent_name"]?.stringValue
                    ?? dict["agentName"]?.stringValue
                    ?? dict["name"]?.stringValue
                    ?? dict["agent_type"]?.stringValue
                    ?? "Unknown"

                let startStr = dict["started_at"]?.stringValue
                    ?? dict["startedAt"]?.stringValue
                    ?? dict["start"]?.stringValue

                let endStr = dict["completed_at"]?.stringValue
                    ?? dict["completedAt"]?.stringValue
                    ?? dict["end"]?.stringValue

                let status = dict["status"]?.stringValue ?? "completed"
                let error = dict["error_message"]?.stringValue ?? dict["errorMessage"]?.stringValue

                var duration: Double = 0
                if let d = dict["duration"]?.doubleValue ?? dict["duration_seconds"]?.doubleValue {
                    duration = d
                } else if let startDate = startStr?.asDate, let endDate = endStr?.asDate {
                    duration = endDate.timeIntervalSince(startDate)
                }

                entries.append(TimelineEntry(
                    displayName: name.replacingOccurrences(of: "_", with: " ").capitalized,
                    startDate: startStr?.asDate,
                    endDate: endStr?.asDate,
                    durationSeconds: duration,
                    status: status,
                    errorMessage: error
                ))
            }
        }

        // Fallback to agentStates
        if entries.isEmpty, let agentStates {
            for state in agentStates {
                let startDate = state.startedAt?.asDate
                let endDate = state.completedAt?.asDate
                var duration: Double = 0
                if let s = startDate, let e = endDate {
                    duration = e.timeIntervalSince(s)
                }

                entries.append(TimelineEntry(
                    displayName: (state.agentName ?? state.agentType ?? "Agent")
                        .replacingOccurrences(of: "_", with: " ").capitalized,
                    startDate: startDate,
                    endDate: endDate,
                    durationSeconds: duration,
                    status: state.status ?? "pending",
                    errorMessage: state.errorMessage
                ))
            }
        }

        return entries.isEmpty ? nil : entries
    }

    // MARK: - Format Duration

    private func formatDuration(_ seconds: Double) -> String {
        if seconds < 60 {
            return String(format: "%.0fs", seconds)
        } else if seconds < 3600 {
            return String(format: "%.0fm", seconds / 60)
        } else {
            return String(format: "%.1fh", seconds / 3600)
        }
    }
}

// MARK: - Timeline Entry

struct TimelineEntry: Identifiable {
    let id = UUID()
    let displayName: String
    let startDate: Date?
    let endDate: Date?
    let durationSeconds: Double
    let status: String
    let errorMessage: String?
}

#Preview {
    ScrollView {
        ExecutionTimelineSection(
            timeline: nil,
            agentStates: nil
        )
        .padding()
    }
    .background(Color.surfaceBackground)
    .preferredColorScheme(.dark)
}
