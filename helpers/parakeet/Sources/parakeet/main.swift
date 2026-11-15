// Batch transcription with Parakeet TDT v3 through FluidAudio.
// usage: parakeet <model-dir> <audio.wav>...
// Loads the model once, then prints one JSON object per file on its own line:
//   {"file":..., "text":..., "duration":..., "tokens":[{"t":..,"s":..,"e":..,"c":..}]}
import CoreML
import FluidAudio
import Foundation

struct Tok: Codable { let t: String; let s: Double; let e: Double; let c: Float }
struct Out: Codable {
    let file: String
    let text: String
    let duration: Double
    let seconds: Double
    let tokens: [Tok]
    let error: String?
}

let args = Array(CommandLine.arguments.dropFirst())
guard args.count >= 2 else {
    FileHandle.standardError.write("usage: parakeet <model-dir> <audio>...\n".data(using: .utf8)!)
    exit(2)
}
let enc = JSONEncoder()

func emit(_ o: Out) {
    if let d = try? enc.encode(o), let s = String(data: d, encoding: .utf8) {
        print(s)
        fflush(stdout)
    }
}

do {
    let dir = URL(fileURLWithPath: args[0])
    // Use the model already on disk; fetch it once if this Mac has never had it.
    let models: AsrModels
    if FileManager.default.fileExists(atPath: dir.appendingPathComponent("Encoder.mlmodelc").path) {
        models = try await AsrModels.load(from: dir)
    } else {
        models = try await AsrModels.downloadAndLoad()
    }
    let mgr = AsrManager(config: .default)
    try await mgr.loadModels(models)
    let layers = await mgr.decoderLayerCount
    for path in args.dropFirst() {
        let t0 = Date()
        do {
            var state = TdtDecoderState.make(decoderLayers: layers)
            let r = try await mgr.transcribe(URL(fileURLWithPath: path), decoderState: &state)
            let toks = (r.tokenTimings ?? []).map {
                Tok(t: $0.token, s: $0.startTime, e: $0.endTime, c: $0.confidence)
            }
            emit(Out(file: path, text: r.text, duration: r.duration,
                     seconds: Date().timeIntervalSince(t0), tokens: toks, error: nil))
        } catch {
            emit(Out(file: path, text: "", duration: 0,
                     seconds: Date().timeIntervalSince(t0), tokens: [], error: "\(error)"))
        }
    }
} catch {
    FileHandle.standardError.write("parakeet: \(error)\n".data(using: .utf8)!)
    exit(1)
}
