import React, { useState, useEffect } from "react";
import useLocalStorage from "./hooks/useLocalStorage";

interface Video {
  id: string;
  title: string;
  published_at: string;
  thumbnail: string;
}

interface Match {
  text: string;
  start: number;
  end: number;
  timestamp: string;
  score: number;
  match_type: "exact" | "partial" | "fuzzy";
}

interface SearchResult {
  video_id: string;
  matches: Match[];
}

interface Toast {
  id: string;
  message: string;
  type: "success" | "error";
}

const API_BASE = import.meta.env.VITE_API_URL || 
  (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
    ? "http://localhost:5000"
    : "");

const getErrorMessage = (error: any, fallback: string): string => {
  if (!error) return fallback;
  if (typeof error === "object") {
    return error.message || error.error || JSON.stringify(error);
  }
  return String(error);
};

export function App() {
  const [channelName, setChannelName] = useState<string>("@AssabiqoonPublisher");
  const [videos, setVideos] = useLocalStorage<Video[]>("cached_videos", []);
  const [selectedVideoIds, setSelectedVideoIds] = useState<string[]>(() => {
    try {
      const cached = localStorage.getItem("cached_videos");
      if (cached) {
        const parsed = JSON.parse(cached);
        if (Array.isArray(parsed)) {
          return parsed.map((v: any) => v.id);
        }
      }
    } catch (e) {}
    return [];
  });
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [threshold, setThreshold] = useState<number>(80);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  
  const [searchHistory, setSearchHistory] = useLocalStorage<string[]>("search_history", []);
  
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Collapsible sections
  const [isFilterExpanded, setIsFilterExpanded] = useState<boolean>(false);
  const [videoSearchText, setVideoSearchText] = useState<string>("");

  // Detailed transcript viewer state
  const [activeTranscriptVideoId, setActiveTranscriptVideoId] = useState<string | null>(null);
  const [fullTranscript, setFullTranscript] = useState<{ text: string; start: number; timestamp: string }[]>([]);
  const [transcriptLoading, setTranscriptLoading] = useState<boolean>(false);

  // Automatically fetch videos on mount
  useEffect(() => {
    fetchVideos(channelName);
  }, []);

  const addToast = (message: string, type: "success" | "error" = "success") => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  };

  const fetchVideos = async (targetChannel: string) => {
    if (!targetChannel.trim()) return;
    
    const hasCache = videos.length > 0;
    if (!hasCache) {
      setLoading(true);
    }
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/channel-videos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel_name: targetChannel.trim() }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(getErrorMessage(data.error, "ไม่สามารถดึงข้อมูลวิดีโอได้"));
      }
      const fetchedVideos = data.videos || [];
      
      const isDifferent = fetchedVideos.length !== videos.length ||
        (fetchedVideos.length > 0 && videos.length > 0 && fetchedVideos[0].id !== videos[0].id);
        
      if (isDifferent || !hasCache) {
        setVideos(fetchedVideos);
        setSelectedVideoIds(fetchedVideos.map((v: Video) => v.id));
        addToast(`อัปเดตรายการวิดีโอเรียบร้อยแล้ว (${fetchedVideos.length} คลิป)`, "success");
      }
    } catch (err: any) {
      if (!hasCache) {
        setError(err.message || "เกิดข้อผิดพลาดในการโหลดวิดีโอ");
      }
    } finally {
      if (!hasCache) {
        setLoading(false);
      }
    }
  };

  const handleSearch = async (e?: React.FormEvent, customQuery?: string) => {
    if (e) e.preventDefault();
    const queryToUse = customQuery !== undefined ? customQuery : searchQuery;
    
    if (!queryToUse.trim()) {
      addToast("กรุณากรอกคำค้นหา", "error");
      return;
    }
    if (selectedVideoIds.length === 0) {
      addToast("กรุณาเลือกวิดีโออย่างน้อย 1 รายการก่อนค้นหา", "error");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video_ids: selectedVideoIds,
          query: queryToUse.trim(),
          threshold: threshold,
          channel_name: channelName.trim(),
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(getErrorMessage(data.error, "เกิดข้อผิดพลาดในการค้นหา"));
      }
      setSearchResults(data.results || []);
      
      const nextHistory = [
        queryToUse.trim(),
        ...searchHistory.filter((q) => q !== queryToUse.trim()),
      ].slice(0, 8);
      setSearchHistory(nextHistory);
      
      addToast(`ค้นหาเสร็จสิ้น พบใน ${data.results.length} วิดีโอ`, "success");
    } catch (err: any) {
      setError(err.message || "เกิดข้อผิดพลาดในการค้นหา");
      addToast("การค้นหาล้มเหลว", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleToggleSelectAll = () => {
    if (selectedVideoIds.length === videos.length) {
      setSelectedVideoIds([]);
    } else {
      setSelectedVideoIds(videos.map((v) => v.id));
    }
  };

  const toggleVideoSelection = (id: string) => {
    setSelectedVideoIds((prev) =>
      prev.includes(id) ? prev.filter((vid) => vid !== id) : [...prev, id]
    );
  };

  const handleCopyLink = (videoId: string, seconds: number) => {
    const url = `https://youtu.be/${videoId}?t=${Math.floor(seconds)}`;
    navigator.clipboard.writeText(url);
    addToast("คัดลอกลิงก์ไปยังคลิปบอร์ดแล้ว!", "success");
  };

  const fetchFullTranscript = async (videoId: string) => {
    setActiveTranscriptVideoId(videoId);
    setTranscriptLoading(true);
    setFullTranscript([]);
    try {
      const response = await fetch(`${API_BASE}/api/video-transcript`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_id: videoId }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(getErrorMessage(data.error, "ไม่สามารถดึง Transcript ได้"));
      
      const formatted = (data.transcript || []).map((t: any) => {
        const start = parseFloat(t.start) || 0;
        return {
          text: t.text,
          start,
          timestamp: formatSeconds(start)
        };
      });
      setFullTranscript(formatted);
    } catch (err: any) {
      addToast(err.message || "การดึง Transcript ล้มเหลว", "error");
      setActiveTranscriptVideoId(null);
    } finally {
      setTranscriptLoading(false);
    }
  };

  const formatSeconds = (seconds: number): string => {
    const secs = Math.floor(seconds);
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const filteredVideosForSelection = videos.filter((v) =>
    v.title.toLowerCase().includes(videoSearchText.toLowerCase())
  );

  return (
    <div className="container">
      {/* Toast container */}
      <div className="toast-container">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast ${toast.type}`}>
            <span>{toast.message}</span>
          </div>
        ))}
      </div>

      {/* Header */}
      <header className="header">
        <h1>YouTube Transcript Search</h1>
        <p>ค้นหาข้อความ คำพูด และเนื้อหาภายในวิดีโอของช่องได้อย่างรวดเร็วและแม่นยำ</p>
      </header>

      {/* Main Search Panel */}
      <div className="search-container">
        <form onSubmit={handleSearch} className="search-box">
          <input
            type="text"
            className="search-input"
            placeholder="พิมพ์ประโยคหรือคำที่ต้องการค้นหา เช่น 'ความศรัทธา', 'น้ำสะอาด'..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? "กำลังค้นหา..." : "ค้นหา"}
          </button>
        </form>

        {/* Status indicator / Summary info */}
        <div className="status-bar">
          <div className="status-badge">
            <span className="dot"></span>
            <span>
              {loading && videos.length === 0
                ? "กำลังดึงรายการวิดีโอ..."
                : `ช่อง: ${channelName} (${selectedVideoIds.length}/${videos.length} คลิปเลือกอยู่)`}
            </span>
          </div>
          {searchHistory.length > 0 && (
            <div className="history-row">
              {searchHistory.map((h, i) => (
                <span
                  key={i}
                  className="history-tag"
                  onClick={() => {
                    setSearchQuery(h);
                    handleSearch(undefined, h);
                  }}
                >
                  {h}
                </span>
              ))}
            </div>
          )}
        </div>

        {error && (
          <div style={{ padding: "0.75rem 1rem", background: "rgba(239, 68, 68, 0.08)", border: "1px solid var(--error)", borderRadius: "8px", fontSize: "0.9rem", color: "var(--error)" }}>
            {error}
          </div>
        )}

        {/* Collapsible Filters Setup */}
        <div className="collapsible-section">
          <div
            className="collapsible-header"
            onClick={() => setIsFilterExpanded(!isFilterExpanded)}
          >
            <span>⚙️ การตั้งค่าและตัวกรองช่อง/วิดีโอ</span>
            <span style={{ fontSize: "0.8rem" }}>{isFilterExpanded ? "▲ ซ่อน" : "▼ แสดง"}</span>
          </div>

          {isFilterExpanded && (
            <div className="collapsible-content">
              {/* Channel Input Field */}
              <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.25rem", alignItems: "flex-end" }}>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.35rem" }}>
                    ชื่อช่อง YouTube
                  </label>
                  <input
                    type="text"
                    className="video-search-input"
                    style={{ margin: 0 }}
                    value={channelName}
                    onChange={(e) => setChannelName(e.target.value)}
                    placeholder="เช่น @AssabiqoonPublisher"
                  />
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ height: "38px", padding: "0 1rem" }}
                  onClick={() => fetchVideos(channelName)}
                  disabled={loading}
                >
                  โหลดใหม่
                </button>
              </div>

              {/* Threshold Settings */}
              <div style={{ marginBottom: "1.25rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.35rem" }}>
                  <span>ระดับความคล้ายคลึงของคำ (Fuzzy Match Threshold)</span>
                  <span>{threshold}%</span>
                </div>
                <input
                  type="range"
                  min="60"
                  max="100"
                  value={threshold}
                  onChange={(e) => setThreshold(parseInt(e.target.value))}
                  style={{ width: "100%", accentColor: "var(--text-primary)" }}
                />
              </div>

              {/* Video selection checklists */}
              <div>
                <div className="video-selection-header">
                  <span style={{ fontSize: "0.85rem", fontWeight: "600" }}>เลือกวิดีโอที่จะค้นหา</span>
                  <button
                    type="button"
                    className="copy-btn"
                    onClick={handleToggleSelectAll}
                  >
                    {selectedVideoIds.length === videos.length ? "ล้างทั้งหมด" : "เลือกทั้งหมด"}
                  </button>
                </div>
                <input
                  type="text"
                  className="video-search-input"
                  placeholder="ค้นหาชื่อวิดีโอในรายการด้านล่างเพื่อเลือก..."
                  value={videoSearchText}
                  onChange={(e) => setVideoSearchText(e.target.value)}
                />
                <div className="video-grid-scroll">
                  {filteredVideosForSelection.length === 0 ? (
                    <div style={{ padding: "1rem", textAlign: "center", fontSize: "0.85rem", color: "var(--text-muted)" }}>
                      ไม่พบวิดีโอที่ตรงกัน
                    </div>
                  ) : (
                    <div className="video-grid">
                      {filteredVideosForSelection.map((video) => {
                        const isSelected = selectedVideoIds.includes(video.id);
                        return (
                          <div
                            key={video.id}
                            className={`video-card ${isSelected ? "selected" : ""}`}
                            onClick={() => toggleVideoSelection(video.id)}
                          >
                            <div className="video-card-checkbox-wrapper">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => {}} // Toggle handled by row click
                              />
                            </div>
                            <img
                              src={video.thumbnail}
                              alt={video.title}
                              className="video-card-thumbnail"
                            />
                            <div className="video-card-info">
                              <span className="video-card-title">{video.title}</span>
                              <span className="video-card-date">{video.published_at}</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Search Results */}
      <div className="results-section">
        {searchResults.length > 0 && (
          <div className="results-header">
            พบผลลัพธ์ทั้งหมด {searchResults.length} วิดีโอ
          </div>
        )}
        
        {searchResults.map((result) => {
          const videoInfo = videos.find((v) => v.id === result.video_id);
          const title = (result as any).title || (videoInfo ? videoInfo.title : result.video_id);
          const thumbnail = (result as any).thumbnail || (videoInfo ? videoInfo.thumbnail : "");
          const isTranscriptMissing = (result as any).transcript_missing;

          return (
            <div key={result.video_id} className="result-card">
              <div className="result-card-header">
                {thumbnail && (
                  <img
                    src={thumbnail}
                    alt={title}
                    className="result-card-thumbnail"
                  />
                )}
                <div className="result-card-info">
                  <h3 className="result-card-title">
                    {title}
                  </h3>
                  <div className="result-card-actions">
                    {!isTranscriptMissing && (
                      <button
                        className="result-card-btn"
                        onClick={() => fetchFullTranscript(result.video_id)}
                      >
                        📖 ดูคำแปล/สคริปต์เต็ม
                      </button>
                    )}
                    <a
                      href={`https://youtu.be/${result.video_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="result-card-btn"
                      style={{ textDecoration: "none" }}
                    >
                      🔗 เปิดใน YouTube
                    </a>
                  </div>
                </div>
              </div>

              <div className="result-matches">
                {isTranscriptMissing ? (
                  <div style={{ padding: "1rem", fontSize: "0.85rem", color: "var(--t3)", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    <span>⚠️ พบคำค้นหาในคลิปนี้บน YouTube (ดึงสคริปต์เวลารายนาทีไม่ได้ชั่วคราวเนื่องจาก YouTube rate limit)</span>
                    <span style={{ fontSize: "0.8rem", color: "var(--t3)" }}>
                      คุณสามารถคลิกปุ่ม "เปิดใน YouTube" ด้านบนเพื่อเปิดดูวิดีโอนี้โดยตรงได้เลยครับ
                    </span>
                  </div>
                ) : (
                  result.matches.map((match, idx) => (
                    <div key={idx} className="match-row">
                      <a
                        href={`https://youtu.be/${result.video_id}?t=${Math.floor(match.start)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="match-time"
                      >
                        ▶ {match.timestamp}
                      </a>
                      <div className="match-text-container">
                        <p className="match-text">"{match.text}"</p>
                        <div className="match-meta">
                          <span className="badge">{match.match_type} ({match.score}%)</span>
                          <span style={{ color: "var(--text-muted)" }}>•</span>
                          <button
                            className="copy-btn"
                            onClick={() => handleCopyLink(result.video_id, match.start)}
                          >
                            คัดลอกลิงก์พร้อมแถมเวลา
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })}

        {searchResults.length === 0 && searchQuery.trim() && !loading && (
          <div style={{ textAlign: "center", padding: "3rem 0", color: "var(--text-muted)" }}>
            ไม่พบคำพูดที่ตรงกับคำค้นหาของคุณ
          </div>
        )}
      </div>

      {/* Transcript Modal Overlay */}
      {activeTranscriptVideoId && (
        <div className="modal-overlay" onClick={() => setActiveTranscriptVideoId(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 style={{ fontSize: "1.1rem", fontWeight: "600" }}>สคริปต์วิดีโอฉบับเต็ม</h3>
              <button
                className="btn btn-secondary"
                style={{ padding: "0.25rem 0.5rem", fontSize: "0.8rem" }}
                onClick={() => setActiveTranscriptVideoId(null)}
              >
                ปิด
              </button>
            </div>
            
            <div className="modal-body">
              {transcriptLoading ? (
                <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
                  กำลังดึงข้อมูลสคริปต์เต็ม...
                </div>
              ) : (
                fullTranscript.map((line, idx) => (
                  <div key={idx} className="transcript-line">
                    <a
                      href={`https://youtu.be/${activeTranscriptVideoId}?t=${Math.floor(line.start)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="transcript-time"
                    >
                      [{line.timestamp}]
                    </a>
                    <p className="transcript-text">{line.text}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
