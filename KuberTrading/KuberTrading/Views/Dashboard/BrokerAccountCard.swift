import SwiftUI

struct BrokerAccountCard: View {
    let account: BrokerAccount

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(account.brokerName.capitalized)
                        .font(.subheadline.weight(.semibold))

                    Text(account.accountType.capitalized)
                        .font(.caption)
                        .foregroundStyle(account.accountType == "live" ? Color.accountLive : Color.accountPaper)
                }

                Spacer()
            }

            Divider()

            if let totalPnl = account.totalPnl {
                LabeledContent("Total P&L") {
                    PnLText(value: totalPnl)
                        .font(.subheadline.weight(.medium))
                }
            }

            if let realizedPnl = account.realizedPnl {
                LabeledContent("Realized") {
                    Text(realizedPnl.currencyFormatted)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let unrealizedPnl = account.unrealizedPnl {
                LabeledContent("Unrealized") {
                    Text(unrealizedPnl.currencyFormatted)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let totalTrades = account.totalTrades {
                LabeledContent("Trades") {
                    Text("\(totalTrades)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 12))
    }
}
