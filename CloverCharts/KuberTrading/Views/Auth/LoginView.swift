import SwiftUI

struct LoginView: View {
    @State private var viewModel = AuthViewModel()
    @State private var showRegister = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 32) {
                    // Logo / Header
                    VStack(spacing: 8) {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                            .font(.system(size: 60))
                            .foregroundStyle(.blue)

                        Text("KuberTrading")
                            .font(.largeTitle.bold())

                        Text("AI-Powered Trading Pipelines")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.top, 40)

                    // Error Banner
                    if let error = viewModel.errorMessage {
                        Text(error)
                            .font(.callout)
                            .foregroundStyle(.white)
                            .padding()
                            .frame(maxWidth: .infinity)
                            .background(Color.red.opacity(0.8), in: RoundedRectangle(cornerRadius: 10))
                    }

                    // Login Form
                    VStack(spacing: 16) {
                        TextField("Email", text: $viewModel.email)
                            .textFieldStyle(.roundedBorder)
                            .textContentType(.emailAddress)
                            .keyboardType(.emailAddress)
                            .autocorrectionDisabled()
                            .textInputAutocapitalization(.never)

                        SecureField("Password", text: $viewModel.password)
                            .textFieldStyle(.roundedBorder)
                            .textContentType(.password)

                        Button {
                            Task { await viewModel.login() }
                        } label: {
                            Group {
                                if viewModel.isLoading {
                                    ProgressView()
                                        .tint(.white)
                                } else {
                                    Text("Sign In")
                                }
                            }
                            .font(.headline)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(viewModel.isLoading)
                    }

                    // Biometric Login
                    if viewModel.showBiometricOption {
                        Button {
                            Task { await viewModel.loginWithBiometric() }
                        } label: {
                            Label("Sign in with Face ID", systemImage: "faceid")
                                .font(.headline)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 14)
                        }
                        .buttonStyle(.bordered)
                    }

                    // Register Link
                    HStack {
                        Text("Don't have an account?")
                            .foregroundStyle(.secondary)
                        Button("Sign Up") {
                            showRegister = true
                        }
                    }
                    .font(.callout)
                }
                .padding(.horizontal, 24)
            }
            .navigationBarHidden(true)
            .navigationDestination(isPresented: $showRegister) {
                RegisterView()
            }
        }
    }
}

#Preview {
    LoginView()
        .preferredColorScheme(.dark)
}
