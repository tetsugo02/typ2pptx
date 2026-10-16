// Video placeholder for typ2pptx.
//
// Write this file into your Typst project with
//
//   typ2pptx --write-video-helper .
//
// and use:
//
//   #import "video.typ": video
//   #video("videos/demo.mp4", poster: "videos/demo.jpg", width: 10cm, height: 5.625cm)
//
// PDF / preview output shows the poster image. typ2pptx reads the
// `<typ2pptx-video>` metadata (physical page, absolute position and size in pt)
// and replaces the poster picture on that slide with the embedded video.
//
// Paths are relative to the Typst project root (`--root`; by default the
// directory of the entry file).

#let _root-path(p) = if p.starts-with("/") { p } else { "/" + p }

#let video(src, poster: none, width: 10cm, height: 5.625cm) = {
  assert(type(src) == str, message: "video(): src must be a path string")
  assert(type(poster) == str, message: "video(): poster image path is required")
  assert(type(width) == length and type(height) == length,
    message: "video(): width and height must be absolute lengths (e.g. 10cm)")
  box(width: width, height: height, {
    // Zero-size anchor at the box's top-left corner; it reports the final
    // page and position after layout.
    place(top + left, context {
      let pos = here().position()
      [#metadata((
        src: src,
        poster: poster,
        page: pos.page,
        x: pos.x.pt(),
        y: pos.y.pt(),
        width: width.to-absolute().pt(),
        height: height.to-absolute().pt(),
      )) <typ2pptx-video>]
    })
    image(_root-path(poster), width: width, height: height, fit: "stretch")
  })
}
