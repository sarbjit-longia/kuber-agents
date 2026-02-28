import SwiftUI

struct ErrorBanner: View {
    let message: String
    var onDismiss: (() -> Void)?

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.white)

            Text(message)
                .font(.callout)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, alignment: .leading)

            if let onDismiss {
                Button {
                    onDismiss()
                } label: {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white.opacity(0.7))
                }
            }
        }
        .padding()
        .background(Color.statusError.opacity(0.9), in: RoundedRectangle(cornerRadius: 10))
        .padding(.horizontal)
    }
}

struct SuccessBanner: View {
    let message: String
    var onDismiss: (() -> Void)?

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.white)

            Text(message)
                .font(.callout)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, alignment: .leading)

            if let onDismiss {
                Button {
                    onDismiss()
                } label: {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white.opacity(0.7))
                }
            }
        }
        .padding()
        .background(Color.statusSuccess.opacity(0.9), in: RoundedRectangle(cornerRadius: 10))
        .padding(.horizontal)
    }
}

#Preview {
    VStack(spacing: 16) {
        ErrorBanner(message: "Failed to load dashboard data.") {}
        SuccessBanner(message: "Pipeline saved successfully.") {}
    }
    .preferredColorScheme(.dark)
}
