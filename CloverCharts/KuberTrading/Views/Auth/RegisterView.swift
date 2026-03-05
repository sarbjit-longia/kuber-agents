import SwiftUI

struct RegisterView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var viewModel = AuthViewModel()

    var body: some View {
        ScrollView {
            VStack(spacing: 32) {
                VStack(spacing: 8) {
                    Image(systemName: "person.badge.plus")
                        .font(.system(size: 50))
                        .foregroundStyle(.blue)

                    Text("Create Account")
                        .font(.largeTitle.bold())

                    Text("Start building trading pipelines")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 20)

                if let error = viewModel.errorMessage {
                    Text(error)
                        .font(.callout)
                        .foregroundStyle(.white)
                        .padding()
                        .frame(maxWidth: .infinity)
                        .background(Color.red.opacity(0.8), in: RoundedRectangle(cornerRadius: 10))
                }

                VStack(spacing: 16) {
                    TextField("Full Name (optional)", text: $viewModel.fullName)
                        .textFieldStyle(.roundedBorder)
                        .textContentType(.name)

                    TextField("Email", text: $viewModel.email)
                        .textFieldStyle(.roundedBorder)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)

                    SecureField("Password", text: $viewModel.password)
                        .textFieldStyle(.roundedBorder)
                        .textContentType(.newPassword)

                    SecureField("Confirm Password", text: $viewModel.confirmPassword)
                        .textFieldStyle(.roundedBorder)
                        .textContentType(.newPassword)

                    Button {
                        Task { await viewModel.register() }
                    } label: {
                        Group {
                            if viewModel.isLoading {
                                ProgressView()
                                    .tint(.white)
                            } else {
                                Text("Create Account")
                            }
                        }
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.isLoading)
                }

                HStack {
                    Text("Already have an account?")
                        .foregroundStyle(.secondary)
                    Button("Sign In") {
                        dismiss()
                    }
                }
                .font(.callout)
            }
            .padding(.horizontal, 24)
        }
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "chevron.left")
                }
            }
        }
    }
}

#Preview {
    NavigationStack {
        RegisterView()
    }
    .preferredColorScheme(.dark)
}
