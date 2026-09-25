---
name: media-forge
description: Generate images and video with the local omni-forge core. Use when the user asks to "make an image", "generate art", "draw", "create a video", or "make an animation" — regardless of phrasing.
---

# Media Forge

Generate images and video through the omni-forge core without leaving opencode.

## Prerequisites
- `forge core` running (see `forge status`). Image generation falls back to the keyless Pollinations API automatically, so it works even with zero local GPUs.
- Optional: ComfyUI + a workflow template set in `FORGE_COMFY_WORKFLOW` for high-quality local rendering.
- Optional: `FORGE_WAN_COMMAND` (Wan 2.1) for video.

## Steps
1. Call the `forge_image` tool with a detailed prompt. Be explicit about style, subject, lighting and composition: `"a cyberpunk cat, neon rain, cinematic lighting, ultra detailed"`.
   - Optional `aspect`: `1:1`, `16:9`, `9:16`, `4:3`, `3:4`.
2. If the user wants a **video**, call `forge_video`/`forge mcp` `forge_video` — it returns a `job_id`. Poll `/v1/video/{job_id}` (via the MCP `forge_video_status` tool) until `status == "done"`.
3. Report the returned URL; it is served by the core at `http://127.0.0.1:4020/media/...`.

## Notes
- The first image call may take 10–60s (ComfyUI queue) or 5–20s (Pollinations).
- Never invent file paths; use the `url`/`path` the backend returns.