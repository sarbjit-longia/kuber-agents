import SwiftUI

struct PnLText: View {
    let value: Double
    var showSign: Bool = true
    var style: PnLStyle = .currency

    enum PnLStyle {
        case currency
        case percent
        case compact
    }

    var body: some View {
        Text(formattedValue)
            .foregroundStyle(Color.pnlColor(for: value))
    }

    private var formattedValue: String {
        switch style {
        case .currency:
            return showSign ? value.pnlFormatted : value.currencyFormatted
        case .percent:
            return value.percentFormatted
        case .compact:
            let sign = showSign && value > 0 ? "+" : ""
            return "\(sign)\(value.compactFormatted)"
        }
    }
}

struct PnLInfoView: View {
    let pnl: PnLInfo?

    var body: some View {
        if let pnl, let value = pnl.value {
            HStack(spacing: 4) {
                PnLText(value: value)
                    .font(.subheadline.weight(.semibold))

                if let percent = pnl.percent {
                    Text("(\(percent.percentFormatted))")
                        .font(.caption)
                        .foregroundStyle(Color.pnlColor(for: percent))
                }
            }
        } else {
            Text("—")
                .foregroundStyle(.secondary)
        }
    }
}

#Preview {
    VStack(spacing: 12) {
        PnLText(value: 1234.56)
        PnLText(value: -567.89)
        PnLText(value: 0)
        PnLText(value: 12.5, style: .percent)
        PnLText(value: -3.2, style: .percent)
        PnLInfoView(pnl: PnLInfo(value: 150.25, percent: 2.5, type: "unrealized"))
        PnLInfoView(pnl: PnLInfo(value: -50.00, percent: -1.2, type: "realized"))
    }
    .padding()
    .preferredColorScheme(.dark)
}
