import SwiftUI

struct ContadorView: View {
    @State private var count = 0

    var body: some View {
        VStack(spacing: 16) {
            Text("\(count)")
                .font(.system(size: 64, weight: .bold, design: .rounded))
            HStack {
                Button("−") { count -= 1 }
                Button("+") { count += 1 }
            }
            .buttonStyle(.borderedProminent)
        }
    }
}
