import SwiftUI

struct MarkdownView: View {
    let content: String

    var body: some View {
        if let attributed = try? AttributedString(markdown: content, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
            Text(attributed)
                .font(.body)
                .textSelection(.enabled)
        } else {
            Text(content)
                .font(.body)
                .textSelection(.enabled)
        }
    }
}

#Preview {
    ScrollView {
        MarkdownView(content: """
        # Heading

        This is **bold** and *italic* text.

        - Item 1
        - Item 2

        `code snippet`
        """)
        .padding()
    }
    .preferredColorScheme(.dark)
}
