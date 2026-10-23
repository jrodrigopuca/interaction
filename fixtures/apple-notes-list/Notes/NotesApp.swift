import SwiftUI
import SwiftData

@main
struct NotesApp: App {
    var body: some Scene {
        WindowGroup {
            NotesListView()
        }
        .modelContainer(for: Note.self)
    }
}
