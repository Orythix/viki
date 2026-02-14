# VIKI Dashboard (React)

Modern, premium dashboard for interacting with VIKI (Virtual Intelligence Knowledge Interface).

## Features

- **Hologram Face (default view)** - Voice conversation with VIKI: hologram-style avatar, browser speech-to-text (microphone), and text-to-speech for responses. Best in Chrome or Edge.
- **Real-time Chat Interface** - Full dashboard: send directives and receive responses (switch via "Full dashboard").
- **Skill Monitor** - View all active skills and their capabilities
- **Model Overview** - See available LLM providers
- **Memory Management** - Clear conversation history
- **Status Monitoring** - Real-time connection status
- **Premium Design** - Dark cyberpunk aesthetic with smooth animations

## Tech Stack

- React 18
- Vite 7
- CSS Variables (No frameworks - maximum flexibility)
- Fetch API for backend communication

## Development

```bash
# Install dependencies (already done by create-vite)
npm install

# Start dev server
npm run dev
```

## Production Build

```bash
npm run build
npm run preview
```

## API Connection

The dashboard connects to VIKI's Flask API server running on `http://localhost:5000`.

Make sure to start the API server before using the dashboard:

```bash
# From VIKI root directory
python viki/api/server.py
```

**Authentication:** All API endpoints require `VIKI_API_KEY`. Set it in your environment; the UI must send `Authorization: Bearer <VIKI_API_KEY>` (or configure the API base to include the key). See [viki/SECURITY_SETUP.md](../viki/SECURITY_SETUP.md).

## Architecture

```
ui/
├── src/
│   ├── App.jsx         # Main application component
│   ├── App.css         # Component-specific styles
│   ├── index.css       # Global design system
│   └── main.jsx        # React entry point
├── index.html          # HTML template
└── vite.config.js      # Vite configuration
```

## Design System

- **Color Palette**: Cyberpunk dark theme with cyan accents
- **Typography**: Inter (sans-serif), JetBrains Mono (monospace)
- **Components**: Glassmorphism effects, glow animations
- **Responsive**: Mobile-first, adapts to all screen sizes

## Environment

Create `ui/.env` (or set build-time env vars) for the UI to talk to the API:

```env
# Same value as VIKI_API_KEY on the server (required for API requests)
VITE_VIKI_API_KEY=your_api_key_here

# Optional: API base URL (default: http://localhost:5000/api)
VITE_VIKI_API_BASE=http://localhost:5000/api
```

- **API endpoint**: Default `http://localhost:5000/api`. Override with `VITE_VIKI_API_BASE`.
- **API key**: Server requires `VIKI_API_KEY`; the UI sends it via `Authorization: Bearer <key>` when `VITE_VIKI_API_KEY` is set. Required for both the dashboard and the Hologram face view.

### AI-generated 3D face (optional)

You can use an **AI-generated or custom 3D face** (GLB/GLTF) for the hologram instead of the built-in procedural face:

1. **Generate a face** with any tool that exports GLB/GLTF, for example:
   - [Luma AI Genie](https://lumalabs.ai/genie) — text-to-3D (e.g. “realistic woman face”)
   - [Meshy](https://meshy.ai), [Tripo3D](https://www.tripo3d.ai), or similar — text/image to 3D
   - [Ready Player Me](https://readyplayer.me) — avatar creator
   - Or download a free head model from [Sketchfab](https://sketchfab.com), [Poly Pizza](https://poly.pizza), etc.

2. **Add the model to the project**: save the file as `ui/public/models/hologram-face.glb` (create the `models` folder if needed).

3. **Point the app at it** via env:
   ```env
   VITE_VIKI_HOLOGRAM_FACE_GLB=/models/hologram-face.glb
   ```
   Or use any full URL to a GLB file.

4. Rebuild or restart the dev server. The hologram view will load the GLB, apply the cyan/purple hologram shader, and center it. If the file is missing or invalid, the built-in procedural face is shown instead.
