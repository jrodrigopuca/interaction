import Foundation
import SwiftData

@Model
final class Note {
    var title: String
    var body: String
    var updatedAt: Date

    init(title: String, body: String = "", updatedAt: Date = .now) {
        self.title = title
        self.body = body
        self.updatedAt = updatedAt
    }
}
