import os
import json
import pytest
from unittest.mock import patch, MagicMock
from backend.utils.youtube import YouTubeClient, retry_with_backoff

def test_retry_decorator():
    calls = []
    
    @retry_with_backoff(retries=2, backoff_in_seconds=0.1)
    def failing_func():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("Transient error")
        return "success"
        
    res = failing_func()
    assert res == "success"
    assert len(calls) == 2

def test_cache_mechanism(tmp_path):
    client = YouTubeClient(cache_dir=str(tmp_path))
    
    # Write and read
    client.db_manager.set_document("transcripts", "test_key", {"data": 123})
    data = client.db_manager.get_document("transcripts", "test_key")
    assert data == {"data": 123}


@patch('backend.utils.youtube.requests.get')
def test_fetch_via_api(mock_get, tmp_path):
    client = YouTubeClient(api_key="fake_key", cache_dir=str(tmp_path))
    
    # Mock handle resolution
    mock_channel_response = MagicMock()
    mock_channel_response.json.return_value = {
        "items": [{
            "contentDetails": {
                "relatedPlaylists": {
                    "uploads": "UUL1v_hQ9QOoc"
                }
            }
        }]
    }
    mock_channel_response.status_code = 200
    
    # Mock playlist items
    mock_playlist_response = MagicMock()
    mock_playlist_response.json.return_value = {
        "items": [{
            "snippet": {
                "resourceId": {"videoId": "vid123"},
                "title": "My Title",
                "publishedAt": "2026-05-10"
            }
        }]
    }
    mock_playlist_response.status_code = 200
    
    mock_get.side_effect = [mock_channel_response, mock_playlist_response]
    
    videos = client._fetch_via_api("@AssabiqoonPublisher", limit=5)
    assert len(videos) == 1
    assert videos[0]["id"] == "vid123"

@patch('backend.utils.youtube.scrapetube.get_channel')
def test_fetch_via_scraping(mock_get_channel, tmp_path):
    client = YouTubeClient(cache_dir=str(tmp_path))
    mock_get_channel.return_value = [
        {
            "videoId": "vid456",
            "publishedTimeText": {"simpleText": "3 days ago"},
            "title": {"runs": [{"text": "Scraped Video"}]}
        }
    ]
    
    videos = client._fetch_via_scraping("Assabiqoon", limit=5)
    assert len(videos) == 1
    assert videos[0]["id"] == "vid456"
    assert videos[0]["title"] == "Scraped Video"

@patch('backend.utils.youtube.YouTubeTranscriptApi.get_transcript')
def test_fetch_video_transcript_live(mock_get_transcript, tmp_path):
    client = YouTubeClient(cache_dir=str(tmp_path))
    
    mock_get_transcript.return_value = [
        {"text": "Hello", "start": 0.0, "duration": 1.0}
    ]
    
    res = client.fetch_video_transcript("live_vid")
    assert len(res) == 1
    assert res[0]["text"] == "Hello"
    assert res[0]["start"] == 0.0
    assert res[0]["duration"] == 1.0

