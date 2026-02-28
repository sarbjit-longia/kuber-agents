import SwiftUI
import Charts

// MARK: - Price Point

struct PricePoint: Identifiable {
    let id = UUID()
    let date: Date
    let price: Double
}

// MARK: - Chart Marker

struct ChartMarker: Identifiable {
    let id = UUID()
    let date: Date
    let price: Double
    let label: String
    let type: MarkerType

    enum MarkerType {
        case entry
        case exit
        case stopLoss
        case takeProfit

        var color: Color {
            switch self {
            case .entry: return .actionBuy
            case .exit: return .actionSell
            case .stopLoss: return .statusError
            case .takeProfit: return .statusSuccess
            }
        }

        var icon: String {
            switch self {
            case .entry: return "arrow.up.right"
            case .exit: return "arrow.down.right"
            case .stopLoss: return "shield.slash"
            case .takeProfit: return "target"
            }
        }
    }
}

// MARK: - Trading Chart View

struct TradingChartView: View {
    let pricePoints: [PricePoint]
    var markers: [ChartMarker] = []
    var title: String?
    var showVolume: Bool = false

    @State private var selectedPoint: PricePoint?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let title {
                Text(title)
                    .font(.subheadline.weight(.semibold))
            }

            if pricePoints.isEmpty {
                emptyView
            } else {
                chartContent
            }

            // Legend for markers
            if !markers.isEmpty {
                markerLegend
            }
        }
        .cardStyle()
    }

    // MARK: - Chart Content

    @ViewBuilder
    private var chartContent: some View {
        Chart {
            // Price line
            ForEach(pricePoints) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("Price", point.price)
                )
                .foregroundStyle(.brandPrimary)
                .interpolationMethod(.monotone)
                .lineStyle(StrokeStyle(lineWidth: 2))
            }

            // Price area gradient
            ForEach(pricePoints) { point in
                AreaMark(
                    x: .value("Date", point.date),
                    y: .value("Price", point.price)
                )
                .foregroundStyle(
                    LinearGradient(
                        colors: [.brandPrimary.opacity(0.2), .brandPrimary.opacity(0.0)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .interpolationMethod(.monotone)
            }

            // Markers
            ForEach(markers) { marker in
                PointMark(
                    x: .value("Date", marker.date),
                    y: .value("Price", marker.price)
                )
                .foregroundStyle(marker.type.color)
                .symbolSize(100)
                .annotation(position: .top, spacing: 4) {
                    VStack(spacing: 2) {
                        Image(systemName: marker.type.icon)
                            .font(.caption2)
                            .foregroundStyle(marker.type.color)
                        Text(marker.label)
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(marker.type.color)
                    }
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(marker.type.color.opacity(0.15), in: RoundedRectangle(cornerRadius: 4))
                }
            }

            // Selected point indicator
            if let selected = selectedPoint {
                RuleMark(x: .value("Date", selected.date))
                    .foregroundStyle(.secondary.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))

                PointMark(
                    x: .value("Date", selected.date),
                    y: .value("Price", selected.price)
                )
                .foregroundStyle(.white)
                .symbolSize(80)
            }
        }
        .chartXAxis {
            AxisMarks(position: .bottom) { _ in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [4]))
                    .foregroundStyle(.secondary.opacity(0.2))
                AxisValueLabel()
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .chartYAxis {
            AxisMarks(position: .trailing) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [4]))
                    .foregroundStyle(.secondary.opacity(0.2))
                AxisValueLabel {
                    if let price = value.as(Double.self) {
                        Text(price.currencyFormatted)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .chartYScale(domain: yDomain)
        .chartOverlay { proxy in
            GeometryReader { geo in
                Rectangle()
                    .fill(Color.clear)
                    .contentShape(Rectangle())
                    .gesture(
                        DragGesture(minimumDistance: 0)
                            .onChanged { value in
                                let origin = geo[proxy.plotFrame!].origin
                                let x = value.location.x - origin.x
                                if let date: Date = proxy.value(atX: x) {
                                    selectedPoint = closestPoint(to: date)
                                }
                            }
                            .onEnded { _ in
                                selectedPoint = nil
                            }
                    )
            }
        }
        .frame(height: 200)

        // Selected point info
        if let selected = selectedPoint {
            HStack {
                Text(selected.date.dateTimeString)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Text(selected.price.currencyFormatted)
                    .font(.caption.weight(.semibold))
            }
        }
    }

    // MARK: - Marker Legend

    @ViewBuilder
    private var markerLegend: some View {
        HStack(spacing: 12) {
            ForEach(markers) { marker in
                HStack(spacing: 4) {
                    Circle()
                        .fill(marker.type.color)
                        .frame(width: 6, height: 6)
                    Text(marker.label)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    // MARK: - Empty View

    private var emptyView: some View {
        VStack(spacing: 8) {
            Image(systemName: "chart.xyaxis.line")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No price data available")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 200)
    }

    // MARK: - Helpers

    private var yDomain: ClosedRange<Double> {
        let prices = pricePoints.map(\.price) + markers.map(\.price)
        guard let minPrice = prices.min(), let maxPrice = prices.max() else {
            return 0...100
        }
        let padding = (maxPrice - minPrice) * 0.15
        return (minPrice - padding)...(maxPrice + padding)
    }

    private func closestPoint(to date: Date) -> PricePoint? {
        pricePoints.min(by: {
            abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date))
        })
    }
}

#Preview {
    let now = Date()
    let points = (0..<50).map { i in
        PricePoint(
            date: now.addingTimeInterval(Double(i) * 3600),
            price: 150 + Double.random(in: -10...10) + Double(i) * 0.2
        )
    }

    let markers = [
        ChartMarker(
            date: points[10].date,
            price: points[10].price,
            label: "Buy",
            type: .entry
        ),
        ChartMarker(
            date: points[35].date,
            price: points[35].price,
            label: "Sell",
            type: .exit
        ),
    ]

    ScrollView {
        TradingChartView(
            pricePoints: points,
            markers: markers,
            title: "AAPL Price"
        )
        .padding()
    }
    .background(Color.surfaceBackground)
    .preferredColorScheme(.dark)
}
