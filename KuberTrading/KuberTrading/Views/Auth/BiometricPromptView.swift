import SwiftUI

struct BiometricPromptView: View {
    let biometricType: BiometricService.BiometricType
    let onEnable: () async -> Void
    let onSkip: () -> Void

    @State private var isLoading = false

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            Image(systemName: biometricIcon)
                .font(.system(size: 80))
                .foregroundStyle(.blue)

            VStack(spacing: 8) {
                Text("Enable \(biometricName)?")
                    .font(.title2.bold())

                Text("Use \(biometricName) for quick and secure access to your trading account.")
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            VStack(spacing: 12) {
                Button {
                    isLoading = true
                    Task {
                        await onEnable()
                        isLoading = false
                    }
                } label: {
                    Group {
                        if isLoading {
                            ProgressView()
                                .tint(.white)
                        } else {
                            Text("Enable \(biometricName)")
                        }
                    }
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                }
                .buttonStyle(.borderedProminent)
                .disabled(isLoading)

                Button("Skip for Now") {
                    onSkip()
                }
                .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding(.horizontal, 32)
    }

    private var biometricIcon: String {
        switch biometricType {
        case .faceID: return "faceid"
        case .touchID: return "touchid"
        case .none: return "lock"
        }
    }

    private var biometricName: String {
        switch biometricType {
        case .faceID: return "Face ID"
        case .touchID: return "Touch ID"
        case .none: return "Biometric"
        }
    }
}

#Preview {
    BiometricPromptView(
        biometricType: .faceID,
        onEnable: {},
        onSkip: {}
    )
    .preferredColorScheme(.dark)
}
