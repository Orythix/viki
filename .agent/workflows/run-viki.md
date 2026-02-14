---
description: Running VIKI Services and Dashboard
---

This workflow guides you through launching the backend API services and the modern React dashboard for VIKI.

### 1. Start the Backend API Server
The API server acts as the bridge between the VIKI Core and the UI. It handles authentication, memory retrieval, and LLM processing. All endpoints require `VIKI_API_KEY` (set in environment).

**Open a new terminal window** and run:
```powershell
# Navigate to the project root
# Ensure your virtual environment is active
.\.venv\Scripts\Activate.ps1

# Start the Flask API Server
python viki/api/server.py
```
*The server will start on `http://localhost:5000`.*

### 2. Start the React Dashboard
The dashboard provides a premium, cyberpunk-themed interface for interacting with VIKI.

**Open a second terminal window** and run:
```powershell
# Navigate to the UI directory
cd ui

# Install dependencies if you haven't already
npm install

# Start the Vite development server
npm run dev
```
*The UI will start on `http://localhost:5173`.*

### 3. Connection Verification
- Open your browser to `http://localhost:5173`.
- Check the **Kernel Diagnostics** in the left sidebar.
- If the status shows **ONLINE**, the UI successfully connected to the backend.
- You can now "Inject command strings" into the input field to interact with VIKI.

### 4. Optional: Run the CLI (Simultaneously)
You can still run the CLI interface while the API is active (they share the same SQLite memory):
```powershell
# In a third terminal
python viki/main.py
```
