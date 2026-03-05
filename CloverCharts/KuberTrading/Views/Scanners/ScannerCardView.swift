import SwiftUI

struct ScannerCardView: View {
    let scanner: Scanner
    let onEdit: () -> Void
    let onDelete: () -> Void
    let onCheckUsage: () async throws -> ScannerUsageResponse

    @State private var showDeleteConfirmation = false
    @State private var usageInfo: ScannerUsageResponse?
    @State private var isCheckingUsage = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header
            HStack(spacing: 8) {
                // Active indicator
                Circle()
                    .fill(scanner.isActive ? Color.statusSuccess : Color.secondary.opacity(0.4))
                    .frame(width: 8, height: 8)

                Text(scanner.name)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)

                Spacer()
            }

            // Type badge
            typeBadge(scanner.scannerType)

            // Stats
            HStack(spacing: 16) {
                statLabel(
                    icon: "number",
                    value: "\(scanner.tickerCount ?? 0)",
                    label: "Tickers"
                )
                statLabel(
                    icon: "arrow.triangle.branch",
                    value: "\(scanner.pipelineCount ?? 0)",
                    label: "Pipelines"
                )
            }

            // Description
            if let description = scanner.description, !description.isEmpty {
                Text(description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            // Last refreshed
            if let lastRefreshed = scanner.lastRefreshedAt {
                Text("Refreshed \(lastRefreshed.formattedRelative)")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding()
        .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 12))
        .contextMenu {
            Button {
                onEdit()
            } label: {
                Label("Edit", systemImage: "pencil")
            }

            Button(role: .destructive) {
                Task { await checkUsageBeforeDelete() }
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
        .confirmationDialog(
            deleteDialogTitle,
            isPresented: $showDeleteConfirmation,
            titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive) {
                onDelete()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            if let usage = usageInfo, usage.pipelineCount > 0 {
                Text("This scanner is used by \(usage.pipelineCount) pipeline(s). Deleting it will affect those pipelines.")
            } else {
                Text("This action cannot be undone.")
            }
        }
    }

    // MARK: - Type Badge

    @ViewBuilder
    private func typeBadge(_ type: String) -> some View {
        let (color, icon) = typeAttributes(type)
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption2)
            Text(type.capitalized)
                .font(.caption2.weight(.medium))
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(color.opacity(0.15), in: Capsule())
        .foregroundStyle(color)
    }

    private func typeAttributes(_ type: String) -> (Color, String) {
        switch type.lowercased() {
        case "manual":
            return (.brandPrimary, "hand.raised")
        case "filter":
            return (.brandSecondary, "line.3.horizontal.decrease.circle")
        case "api":
            return (.statusInfo, "network")
        default:
            return (.secondary, "questionmark.circle")
        }
    }

    // MARK: - Stat Label

    @ViewBuilder
    private func statLabel(icon: String, value: String, label: String) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.weight(.semibold))
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Usage Check

    private var deleteDialogTitle: String {
        if isCheckingUsage { return "Checking usage..." }
        if let usage = usageInfo, usage.pipelineCount > 0 {
            return "Scanner In Use"
        }
        return "Delete Scanner?"
    }

    private func checkUsageBeforeDelete() async {
        isCheckingUsage = true
        do {
            usageInfo = try await onCheckUsage()
        } catch {
            usageInfo = nil
        }
        isCheckingUsage = false
        showDeleteConfirmation = true
    }
}

#Preview {
    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
        ScannerCardView(
            scanner: Scanner(
                id: "1",
                userId: "user1",
                name: "Tech Stocks",
                description: "Major tech companies",
                scannerType: "manual",
                config: [:],
                isActive: true,
                refreshInterval: nil,
                lastRefreshedAt: nil,
                createdAt: "",
                updatedAt: "",
                tickerCount: 15,
                pipelineCount: 3
            ),
            onEdit: {},
            onDelete: {},
            onCheckUsage: { ScannerUsageResponse(pipelineCount: 0, pipelines: []) }
        )

        ScannerCardView(
            scanner: Scanner(
                id: "2",
                userId: "user1",
                name: "S&P 500 Filter",
                description: nil,
                scannerType: "filter",
                config: [:],
                isActive: false,
                refreshInterval: 3600,
                lastRefreshedAt: nil,
                createdAt: "",
                updatedAt: "",
                tickerCount: 50,
                pipelineCount: 0
            ),
            onEdit: {},
            onDelete: {},
            onCheckUsage: { ScannerUsageResponse(pipelineCount: 0, pipelines: []) }
        )
    }
    .padding()
    .preferredColorScheme(.dark)
}
