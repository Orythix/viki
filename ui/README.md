# VIKI Dashboard (React)

Modern, premium dashboard for interacting with VIKI (Virtual Intelligence Knowledge Interface).

## Features

- **Real-time Chat Interface** - Send directives and receive responses
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

No environment variables required. API endpoint is hardcoded to `http://localhost:5000/api`.

For production, update `API_BASE` in `src/App.jsx`.
