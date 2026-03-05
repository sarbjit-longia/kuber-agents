import SwiftUI

struct ProfileSettingsView: View {
    @Bindable var viewModel: SettingsViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var isSaving = false

    var body: some View {
        Form {
            // Error / Success
            if let error = viewModel.errorMessage {
                Section {
                    Text(error)
                        .font(.subheadline)
                        .foregroundStyle(.statusError)
                }
            }

            if let success = viewModel.successMessage {
                Section {
                    Text(success)
                        .font(.subheadline)
                        .foregroundStyle(.statusSuccess)
                }
            }

            // Profile Fields
            Section("Personal Information") {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Full Name")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField("Enter your full name", text: $viewModel.fullName)
                        .textContentType(.name)
                        .textInputAutocapitalization(.words)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("Email")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField("Enter your email", text: $viewModel.email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
            }

            // Account info (read-only)
            Section("Account") {
                HStack {
                    Text("Account ID")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text(viewModel.user?.id.prefix(8).appending("...") ?? "N/A")
                        .font(.caption.monospaced())
                        .foregroundStyle(.tertiary)
                }

                HStack {
                    Text("Member Since")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text(viewModel.user?.createdAt.formattedDate ?? "N/A")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Text("Status")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Spacer()
                    HStack(spacing: 4) {
                        Circle()
                            .fill(viewModel.user?.isActive == true ? Color.statusSuccess : Color.statusError)
                            .frame(width: 8, height: 8)
                        Text(viewModel.user?.isActive == true ? "Active" : "Inactive")
                            .font(.subheadline)
                    }
                }
            }

            // Save
            Section {
                Button {
                    Task {
                        isSaving = true
                        await viewModel.updateProfile()
                        isSaving = false
                    }
                } label: {
                    HStack {
                        Spacer()
                        if isSaving {
                            ProgressView()
                                .scaleEffect(0.8)
                        } else {
                            Text("Save Changes")
                                .font(.body.weight(.semibold))
                        }
                        Spacer()
                    }
                }
                .disabled(isSaving || !hasChanges)
            }
        }
        .scrollContentBackground(.hidden)
        .background(Color.surfaceBackground)
        .navigationTitle("Profile")
        .navigationBarTitleDisplayMode(.inline)
    }

    // MARK: - Helpers

    private var hasChanges: Bool {
        let nameChanged = viewModel.fullName != (viewModel.user?.fullName ?? "")
        let emailChanged = viewModel.email != (viewModel.user?.email ?? "")
        return nameChanged || emailChanged
    }
}

#Preview {
    NavigationStack {
        ProfileSettingsView(viewModel: SettingsViewModel())
    }
    .preferredColorScheme(.dark)
}
