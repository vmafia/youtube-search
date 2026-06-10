# Cloud Deployment Guide

This document outlines different deployment patterns for launching the YouTube Transcript Search application on cloud infrastructures.

---

## 1. Single Node Docker Deployment (VPS/EC2)
This is the simplest way to deploy. You can provision a small VM (AWS EC2, DigitalOcean Droplet, Linode) and run using Docker Compose.

### Steps:
1. Clone the repository onto the server.
2. Install Docker and Docker Compose on the server.
3. Configure the `.env` variables (ensure to set a secure `SECRET_KEY` and your `YOUTUBE_API_KEY`).
4. Boot the system:
   ```bash
   docker-compose up -d --build
   ```
5. Configure reverse proxy (Nginx or Caddy) to redirect traffic from domains to ports `3000` (frontend) and `5000` (backend /api).

---

## 2. Render Deployment (PaaS)
Render is an excellent option for free/low-cost automated Git-backed builds.

### Backend (Flask):
1. Create a **Web Service** on Render.
2. Link your Git repository.
3. Configure runtime to `Python`.
4. Set Build Command: `pip install -r backend/requirements.txt`
5. Set Start Command: `gunicorn --bind 0.0.0.0:10000 --chdir backend app:app`
6. Set Environment Variables:
   - `FLASK_ENV` = `production`
   - `SECRET_KEY` = `your-secure-production-key`
   - `YOUTUBE_API_KEY` = `your-api-key-here`

### Frontend (React Static Site):
1. Create a **Static Site** on Render.
2. Link your Git repository.
3. Set Build Command: `cd frontend && npm install && npm run build`
4. Set Publish Directory: `frontend/dist`
5. Set Environment Variables:
   - `VITE_API_URL` = `https://your-backend-render-url.onrender.com`

---

## 3. Production Hardening
- **Cache Persistence**: Ensure the `backend/cache` directory is mounted on a persistent volume so transcripts remain cached across container restarts.
- **YouTube API Quotas**: The default daily quota for YouTube API v3 is 10,000 units. A channel video query consumes 1 unit (via playlistItems). If quota is exceeded, the application transparently falls back to scrapetube.
- **SSL Certificates**: Always run the frontend and API endpoints behind HTTPS using Let's Encrypt to protect clipboard interaction and browser communication.
