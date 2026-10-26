# HUD video reference

User-selected source:
https://v1.pinimg.com/videos/iht/hls/48/19/33/4819336a5f5cde35f9fdf77103c42b8f_720w.cmfv

The provided resource contains a decodable H.264 video stream, 720×720, duration 10.01 s.
`hud_reference.mp4` preserves that stream without re-encoding and uses a fast-start MP4
container, with no audio tracks. The application plays this local file silently in a loop.
Keep the `assets` directory beside the source entrypoint (or frozen executable).
