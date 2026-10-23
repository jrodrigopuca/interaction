import Foundation
import SwiftData

@Model
final class Note {
    var title: String
    var body: String
    var updatedAt: Date
    var tags: [String]?

    init(title: String, body: String = "", updatedAt: Date = .now, tags: [String]? = nil) {
        self.title = title
        self.body = body
        self.updatedAt = updatedAt
        self.tags = tags
    }
}
