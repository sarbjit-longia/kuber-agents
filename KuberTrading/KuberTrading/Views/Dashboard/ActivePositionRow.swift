import SwiftUI

struct ActivePositionRow: View {
    let position: ActivePosition
    var onTap: (() -> Void)?

    var body: some View {
        Button {
            onTap?()
        } label: {
            HStack(spacing: 12) {
                // Symbol & Pipeline
                VStack(alignment: .leading, spacing: 2) {
                    Text(position.symbol ?? "")
                        .font(.subheadline.weight(.semibold))

                    Text(position.pipelineName)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer()

                // Trade side
                if let side = position.tradeInfo?.side {
                    Text(side.uppercased())
                        .font(.caption.weight(.bold))
                        .foregroundStyle(side.lowercased() == "buy" ? Color.actionBuy : Color.actionSell)
                }

                // P&L
                PnLInfoView(pnl: position.pnl)

                // Status
                StatusBadge(status: position.status, size: .small)
            }
            .padding(.vertical, 8)
        }
        .buttonStyle(.plain)
    }
}
