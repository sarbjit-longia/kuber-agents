import SwiftUI

struct ScannerListView: View {
    @State private var viewModel = ScannerViewModel()

    private let columns = [
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12),
    ]

    var body: some View {
        ScrollView {
            if viewModel.isLoading && viewModel.scanners.isEmpty {
                LoadingView(message: "Loading scanners...")
            } else if viewModel.scanners.isEmpty {
                EmptyStateView(
                    icon: "antenna.radiowaves.left.and.right",
                    title: "No Scanners",
                    message: "Create a scanner to define ticker groups for your pipelines.",
                    actionTitle: "Create Scanner"
                ) {
                    viewModel.resetForm()
                    viewModel.showCreateSheet = true
                }
            } else {
                LazyVStack(spacing: 16) {
                    // Error banner
                    if let error = viewModel.errorMessage {
                        ErrorBanner(message: error) {
                            viewModel.errorMessage = nil
                        }
                    }

                    // Scanner grid
                    LazyVGrid(columns: columns, spacing: 12) {
                        ForEach(viewModel.scanners) { scanner in
                            ScannerCardView(
                                scanner: scanner,
                                onEdit: {
                                    viewModel.prepareEdit(scanner: scanner)
                                },
                                onDelete: {
                                    Task { await viewModel.deleteScanner(id: scanner.id) }
                                },
                                onCheckUsage: {
                                    try await viewModel.checkUsage(id: scanner.id)
                                }
                            )
                        }
                    }
                    .padding(.horizontal)
                }
                .padding(.top, 8)
                .padding(.bottom, 40)
            }
        }
        .background(Color.surfaceBackground)
        .refreshable {
            await viewModel.loadScanners()
        }
        .navigationTitle("Scanners")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    viewModel.resetForm()
                    viewModel.showCreateSheet = true
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $viewModel.showCreateSheet) {
            CreateScannerSheet(viewModel: viewModel)
        }
        .task {
            await viewModel.loadScanners()
        }
    }
}

#Preview {
    NavigationStack {
        ScannerListView()
    }
    .preferredColorScheme(.dark)
}
