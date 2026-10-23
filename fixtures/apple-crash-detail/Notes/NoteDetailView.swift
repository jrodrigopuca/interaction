import SwiftUI

struct NoteDetailView: View {
    let note: Note

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text(note.title)
                    .font(.largeTitle.bold())
                Text(note.body)
                HStack {
                    Label(note.tags!.first!, systemImage: "tag")
                        .font(.caption)
                }
            }
            .padding()
        }
    }
}
