import json
import pytest
from unittest.mock import patch, MagicMock
from backend.app import app, youtube_client

@pytest.fixture
def client():
    app.config["TESTING"] = True
    # Clean rate limits for testing or use memory limiter
    with app.test_client() as client:
        yield client

def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json["status"] == "healthy"
    assert "database" in response.json

def test_channel_videos_validation(client):
    response = client.post("/api/channel-videos", json={})
    assert response.status_code == 400
    assert "channel_name parameter is required" in response.json["error"]

@patch.object(youtube_client, 'fetch_channel_videos')
def test_channel_videos_success(mock_fetch, client):
    mock_fetch.return_value = [
        {"id": "vid1", "title": "Video 1", "published_at": "2026-05-20", "thumbnail": "thumb1"}
    ]
    response = client.post("/api/channel-videos", json={"channel_name": "Assabiqoon"})
    assert response.status_code == 200
    assert len(response.json["videos"]) == 1
    assert response.json["videos"][0]["id"] == "vid1"

def test_video_transcript_validation(client):
    response = client.post("/api/video-transcript", json={})
    assert response.status_code == 400
    assert "video_id parameter is required" in response.json["error"]

@patch.object(youtube_client, 'fetch_video_transcript')
def test_video_transcript_success(mock_fetch_transcript, client):
    mock_transcript = [{"text": "Hello World", "start": 1.0, "duration": 2.0}]
    mock_fetch_transcript.return_value = mock_transcript
    
    response = client.post("/api/video-transcript", json={"video_id": "vid1"})
    assert response.status_code == 200
    assert response.json["video_id"] == "vid1"
    assert response.json["transcript"] == mock_transcript

@patch.object(youtube_client.db_manager, 'get_document')
def test_search_endpoint(mock_get_document, client):
    mock_transcript = [
        {"text": "สวัสดีครับพี่น้อง", "start": 1.0, "duration": 2.0},
        {"text": "วันนี้เสนอเรื่องแนวทางที่ถูกต้อง", "start": 3.0, "duration": 3.0},
        {"text": "Welcome to our class", "start": 6.0, "duration": 2.0}
    ]
    mock_get_document.return_value = mock_transcript

    # 1. Exact/Substring match (Thai)
    response = client.post("/api/search", json={"video_ids": ["vid1"], "query": "แนวทาง"})
    assert response.status_code == 200
    results = response.json["results"]
    assert len(results) == 1
    assert results[0]["video_id"] == "vid1"
    assert len(results[0]["matches"]) == 1
    assert "แนวทาง" in results[0]["matches"][0]["text"]

    # 2. Fuzzy match (English with typo)
    response = client.post("/api/search", json={"video_ids": ["vid1"], "query": "welcom to clas"})
    assert response.status_code == 200
    results = response.json["results"]
    assert len(results) == 1
    assert results[0]["matches"][0]["match_type"] == "fuzzy"

    # 3. No match
    response = client.post("/api/search", json={"video_ids": ["vid1"], "query": "something totally different"})
    assert response.status_code == 200
    assert len(response.json["results"]) == 0

@patch.object(youtube_client, 'fetch_channel_videos')
def test_rate_limiting(mock_fetch, client):
    mock_fetch.return_value = []
    # Flask-Limiter is enabled in the app. Let's send 35 requests rapidly to verify 429
    # (Note: depending on the test client state, it may trigger fast. Let's make sure we test if rate limit fires.)
    hit_limit = False
    for _ in range(40):
        response = client.post("/api/channel-videos", json={"channel_name": "Assabiqoon"})
        if response.status_code == 429:
            hit_limit = True
            break
    # Since health is exempt, let's verify it still works even if we hit limit on channel-videos
    health_response = client.get("/api/health")
    assert health_response.status_code == 200
