import SwiftUI

struct ExecutionFilterBar: View {
    let selectedFilter: String?
    let onFilterChanged: (String?) -> Void

    private let filters: [(key: String?, label: String)] = [
        (nil, "All"),
        ("TRADED", "Traded"),
        ("RUNNING", "Running"),
        ("MONITORING", "Monitoring"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
        ("AWAITING_APPROVAL", "Awaiting Approval"),
    ]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(filters, id: \.label) { filter in
                    filterPill(key: filter.key, label: filter.label)
                }
            }
            .padding(.horizontal)
        }
    }

    private func filterPill(key: String?, label: String) -> some View {
        let isSelected = selectedFilter == key

        return Button {
            onFilterChanged(key)
        } label: {
            HStack(spacing: 6) {
                if let key {
                    Circle()
                        .fill(key == "TRADED" ? Color.statusSuccess : Color.executionStatusColor(key))
                        .frame(width: 6, height: 6)
                }

                Text(label)
                    .font(.caption.weight(isSelected ? .semibold : .regular))
            }
            .foregroundStyle(isSelected ? .white : .secondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(
                isSelected
                    ? (key == "TRADED" ? Color.statusSuccess : key != nil ? Color.executionStatusColor(key!) : Color.brandPrimary)
                    : Color.surfaceElevated,
                in: Capsule()
            )
        }
        .buttonStyle(.plain)
    }
}

#Preview {
    VStack(spacing: 20) {
        ExecutionFilterBar(selectedFilter: nil, onFilterChanged: { _ in })
        ExecutionFilterBar(selectedFilter: "RUNNING", onFilterChanged: { _ in })
        ExecutionFilterBar(selectedFilter: "COMPLETED", onFilterChanged: { _ in })
    }
    .padding(.vertical)
    .preferredColorScheme(.dark)
}
