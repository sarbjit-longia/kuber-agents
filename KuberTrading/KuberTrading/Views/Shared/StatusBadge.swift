import SwiftUI

struct StatusBadge: View {
    let status: String
    var size: BadgeSize = .regular

    enum BadgeSize {
        case small, regular, large

        var font: Font {
            switch self {
            case .small: return .caption2
            case .regular: return .caption
            case .large: return .callout
            }
        }

        var padding: EdgeInsets {
            switch self {
            case .small: return EdgeInsets(top: 2, leading: 6, bottom: 2, trailing: 6)
            case .regular: return EdgeInsets(top: 4, leading: 8, bottom: 4, trailing: 8)
            case .large: return EdgeInsets(top: 6, leading: 12, bottom: 6, trailing: 12)
            }
        }
    }

    var body: some View {
        Text(displayText)
            .font(size.font.weight(.semibold))
            .foregroundStyle(foregroundColor)
            .padding(size.padding)
            .background(backgroundColor, in: Capsule())
    }

    private var displayText: String {
        status.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private var foregroundColor: Color {
        Color.executionStatusColor(status)
    }

    private var backgroundColor: Color {
        foregroundColor.opacity(0.15)
    }
}

#Preview {
    VStack(spacing: 12) {
        StatusBadge(status: "completed")
        StatusBadge(status: "running")
        StatusBadge(status: "failed")
        StatusBadge(status: "monitoring")
        StatusBadge(status: "awaiting_approval")
        StatusBadge(status: "pending", size: .small)
        StatusBadge(status: "cancelled", size: .large)
    }
    .padding()
    .preferredColorScheme(.dark)
}
