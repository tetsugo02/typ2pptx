// typ2pptx examples/video/slides.typ -o slides.pptx
//
// The video and poster are not committed; create them first, e.g. with FFmpeg
// (H.264 + AAC MP4), from the examples/video directory:
//
//   mkdir -p videos
//   ffmpeg -f lavfi -i testsrc=size=1280x720:rate=30:duration=6 \
//     -f lavfi -i sine=frequency=440:duration=6 -shortest \
//     -c:v libx264 -pix_fmt yuv420p -c:a aac -movflags +faststart videos/demo.mp4
//   ffmpeg -ss 1 -i videos/demo.mp4 -frames:v 1 videos/demo.jpg
#import "@preview/touying:0.7.4": *
#import themes.simple: *
#import "video.typ": video

#show: simple-theme.with(aspect-ratio: "16-9")

== Embedded video

- `#video(...)` shows the poster image in PDF output.
- typ2pptx replaces the poster with the embedded video (click to play).

== Centered video

#align(center, video(
  "videos/demo.mp4",
  poster: "videos/demo.jpg",
  width: 10cm,
  height: 5.625cm,
))

== Video after a pause

The video appears on the second subslide only.

#pause

#video("videos/demo.mp4", poster: "videos/demo.jpg", width: 8cm, height: 4.5cm)
