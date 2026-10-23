import SwiftUI
import SwiftData

struct NotesListView: View {
    @Query(sort: \Note.updatedAt, order: .reverse) private var notes: [Note]
    @Environment(\.modelContext) private var modelContext

    var body: some View {
        NavigationStack {
            List(notes) { note in
                VStack(alignment: .leading, spacing: 4) {
                    Text(note.title)
                        .font(.headline)
                    Text(note.updatedAt, style: .relative)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Notas")
            .toolbar {
                Button("Nueva", systemImage: "plus") {
                    modelContext.insert(Note(title: "Nota nueva"))
                }
            }
        }
    }
}
