---
description: How to generate viral short-form video projects (JSON)
---

VIKI can now function as an autonomous AI workflow agent for creating viral short-form videos.

### 1. Generating a Video Project
To start the workflow, ask VIKI to generate a video for a specific topic:
```bash
/short productivity hacks
```
Or:
```bash
Generate a viral video script about the future of space exploration.
```

### 2. Output Format
VIKI will trigger the `short_video_agent` and return a structured JSON object containing:
- `video_title`: Catchy title
- `video_theme`: Core theme
- `duration_seconds`: 20-40s
- `scenes`: Narration and Stable Diffusion prompts for each scene
- `captions`: Platform-specific captions (IG, YT, TikTok)
- `hashtags`: Optimized growth hashtags

### 3. Downstream Processing
The generated JSON is designed to be automation-friendly. You can pipe the output to video assembly scripts or image generation pipelines.

Example usage with the `short` alias:
```viki
short topic="top 5 python secrets"
```
