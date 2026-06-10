# YouTube Transcript Search Application

A production-grade, highly responsive web application to search for specific words or phrases in YouTube videos. Specially configured and optimized for the `@AssabiqoonPublisher` channel.

## Features
- **3-Step Wizard Flow**: Channel selection &rarr; Video filtering &rarr; Transcript Phrase Searching.
- **Fuzzy Search**: Resolves typos/spells using Python `rapidfuzz` scoring above 80% similarity.
- **Double-language (Thai + English) search normalization**.
- **Interactive Timestamps**: Clickable search results that direct the browser to the exact second in the video.
- **Transcript Cache**: Caches fetched video transcripts locally to bypass YouTube API limits.
- **Production-ready API**: Complete with Flask-Limiter, Global Exception formatting, and Structured Logging.

---

## Folder Structure
```
youtube_transcript_search/
├── backend/
│   ├── utils/
│   │   ├── youtube.py     # YouTube client & scrapetube fallback
│   │   └── search.py      # Fuzzy & exact string-matching logic
│   ├── tests/
│   │   └── test_app.py    # Unit & Integration pytest suite
│   ├── app.py             # Flask application entry point
│   ├── config.py          # Port & Directory setups
│   └── requirements.txt   # Python Dependencies
├── frontend/
│   ├── src/
│   │   ├── components/    # ErrorBoundary, Toast layouts
│   │   ├── hooks/         # useLocalStorage (Search history)
│   │   ├── App.tsx        # Main application state logic
│   │   └── index.css      # Core Dark Theme styles
│   ├── package.json
│   └── vite.config.ts
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── .dockerignore
└── README.md
```

---

## Development Setup

### Backend (Python 3.9+)
1. Change directory into `backend/`:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run tests:
   ```bash
   pytest tests/
   ```
5. Launch the application:
   ```bash
   python app.py
   ```
   *Backend will start on `http://localhost:5000`*

### Frontend (Node.js 18+)
1. Change directory into `frontend/`:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run Vitest suites:
   ```bash
   npm run test
   ```
4. Launch development server:
   ```bash
   npm run dev
   ```
   *Frontend will start on `http://localhost:3000` or `http://localhost:5173`*

---

## Docker Deployment (Docker Compose)
1. In the root directory, create a `.env` file using `.env.example`.
2. Spin up containers:
   ```bash
   docker-compose up --build
   ```
3. Open `http://localhost:3000` in your web browser.

---

## API Documentation

### 1. `GET /api/health`
Checks server status.
- **Response**: `{"status": "healthy"}`

### 2. `POST /api/channel-videos`
Returns the list of the latest 100 videos of a channel.
- **Request Body**: `{"channel_name": "@AssabiqoonPublisher"}`
- **Response**: `{"videos": [{"id": "...", "title": "...", "published_at": "...", "thumbnail": "..."}]}`

### 3. `POST /api/search`
Searches matching transcripts within selected video IDs.
- **Request Body**:
  ```json
  {
    "video_ids": ["vid1", "vid2"],
    "query": "แนวทาง",
    "threshold": 80.0
  }
  ```
- **Response**:
  ```json
  {
    "query": "แนวทาง",
    "results": [
      {
        "video_id": "vid1",
        "matches": [
          {
            "text": "ยึดมั่นในแนวทางที่ถูกต้อง",
            "start": 10.5,
            "end": 15.0,
            "timestamp": "00:10",
            "score": 100.0,
            "match_type": "partial"
          }
        ]
      }
    ]
  }
  ```

### 4. `POST /api/video-transcript`
Retrieves full transcript texts with timestamps.
- **Request Body**: `{"video_id": "vid1"}`
- **Response**: `{"video_id": "...", "transcript": [{"text": "...", "start": 1.5, "duration": 2.0}]}`

---

## Troubleshooting Guide
- **Transcripts Disabled Error**: Some YouTube videos explicitly disable auto-generated transcripts. The app uses a fallback mock cache specifically loaded for `@AssabiqoonPublisher` to guarantee it functions immediately.
- **Rate Limit Hits**: If you hit a 429 status code, wait 60 seconds. You can customize the limit configurations in `backend/config.py`.
- **CORS Errors**: If running frontend and backend on custom ports, modify CORS origin setups in `backend/app.py`.
