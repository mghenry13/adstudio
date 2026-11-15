// track: camera motion of a video span, for text that moves with the footage.
//
// usage: track <video> <start-seconds> <duration-seconds>
// prints one JSON line per frame: {"t": seconds from start, "x": .., "y": ..}
// x and y are how far the scene has moved since the first frame, as a
// fraction of the frame's width and height (positive = right and down).
// Uses Apple Vision's translational image registration between frames.

import AVFoundation
import CoreImage
import Foundation
import Vision

let args = CommandLine.arguments
guard args.count >= 4, let start = Double(args[2]), let dur = Double(args[3]) else {
    FileHandle.standardError.write("usage: track <video> <start> <duration>\n".data(using: .utf8)!)
    exit(2)
}
let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
guard let reader = try? AVAssetReader(asset: asset),
      let vtrack = asset.tracks(withMediaType: .video).first else {
    FileHandle.standardError.write("cannot read video\n".data(using: .utf8)!)
    exit(1)
}
reader.timeRange = CMTimeRange(start: CMTime(seconds: start, preferredTimescale: 600),
                               duration: CMTime(seconds: dur, preferredTimescale: 600))
let out = AVAssetReaderTrackOutput(track: vtrack, outputSettings: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
out.alwaysCopiesSampleData = false
reader.add(out)
reader.startReading()

// Work on a small copy: registration is about the whole scene, not detail.
let ctx = CIContext(options: [.useSoftwareRenderer: false])
let target: CGFloat = 270
var prev: CGImage? = nil
var cx = 0.0, cy = 0.0
var t0: Double? = nil
var w = 1.0, h = 1.0
let transform = vtrack.preferredTransform

while let sample = out.copyNextSampleBuffer() {
    guard let pb = CMSampleBufferGetImageBuffer(sample) else { continue }
    let pts = CMSampleBufferGetPresentationTimeStamp(sample).seconds
    if t0 == nil { t0 = pts }
    var ci = CIImage(cvPixelBuffer: pb).transformed(by: transform)
    ci = ci.transformed(by: CGAffineTransform(translationX: -ci.extent.origin.x, y: -ci.extent.origin.y))
    let s = target / ci.extent.width
    ci = ci.transformed(by: CGAffineTransform(scaleX: s, y: s))
    guard let img = ctx.createCGImage(ci, from: ci.extent) else { continue }
    w = Double(img.width); h = Double(img.height)
    if let p = prev {
        let req = VNTranslationalImageRegistrationRequest(targetedCGImage: img, options: [:])
        let handler = VNImageRequestHandler(cgImage: p, options: [:])
        if (try? handler.perform([req])) != nil,
           let obs = req.results?.first as? VNImageTranslationAlignmentObservation {
            // Transform that moves the new frame onto the previous one; the scene
            // moved the opposite way. Vision's y axis points up.
            let tr = obs.alignmentTransform
            cx += -Double(tr.tx) / w
            cy += Double(tr.ty) / h
        }
    }
    prev = img
    print(String(format: "{\"t\": %.4f, \"x\": %.5f, \"y\": %.5f}", pts - (t0 ?? pts), cx, cy))
}
