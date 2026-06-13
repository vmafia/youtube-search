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
  match_type: "exact" | "partial" | "fuzzy" | "estimated";
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
  const [localThreshold, setLocalThreshold] = useState<number>(80);
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

  // Tab and Dashboard state
  interface StatsData {
    transcribed_count: number;
    no_subtitle_count: number;
    transcribed_ids: string[];
  }
  interface TranscriptionStatus {
    status: "running" | "idle";
    current_index: number;
    total_to_process: number;
    current_video_id: string;
    current_video_title: string;
    progress_state: string;
    success_count: number;
    fail_count: number;
    last_updated: number;
  }
  const [activeTab, setActiveTab] = useState<"search" | "dashboard">("search");
  const [stats, setStats] = useState<StatsData | null>(null);
  const [statsLoading, setStatsLoading] = useState<boolean>(false);
  const [dashboardSearchText, setDashboardSearchText] = useState<string>("");
  const [transcriptionStatus, setTranscriptionStatus] = useState<TranscriptionStatus | null>(null);
  const [filterType, setFilterType] = useState<"all" | "transcribed" | "pending">("all");

  // Automatically fetch videos on mount
  useEffect(() => {
    fetchVideos(channelName);
  }, []);

  const fetchStats = async () => {
    setStatsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/transcription-stats`);
      if (!response.ok) throw new Error("ไม่สามารถดึงข้อมูลสถิติได้");
      const data = await response.json();
      setStats(data);
    } catch (err: any) {
      addToast(err.message || "โหลดสถิติล้มเหลว", "error");
    } finally {
      setStatsLoading(false);
    }
  };

  const fetchTranscriptionStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/transcription-status`);
      if (response.ok) {
        const data = await response.json();
        setTranscriptionStatus(data);
      }
    } catch (err) {
      console.error("Failed to fetch transcription status:", err);
    }
  };

  const getProgressStateLabel = (state: string): string => {
    switch (state) {
      case "starting": return "กำลังเริ่มระบบประมวลผล...";
      case "downloading": return "📥 กำลังดาวน์โหลดไฟล์เสียงจาก YouTube...";
      case "uploading_gemini": return "📤 กำลังอัปโหลดเสียงขึ้นระบบคลาวด์ Gemini...";
      case "processing_gemini": return "⚙️ Gemini กำลังเตรียมประมวลผลไฟล์เสียง...";
      case "generating_transcript": return "🧠 Gemini กำลังประมวลผลถอดความเป็นภาษาไทย...";
      case "success": return "✓ ถอดความสคริปต์สำเร็จและบันทึกลงฐานข้อมูลแล้ว";
      case "save_failed": return "✗ บันทึกสคริปต์ลงฐานข้อมูลล้มเหลว";
      case "transcription_failed": return "✗ ถอดความสคริปต์ล้มเหลว";
      case "download_failed": return "✗ ดาวน์โหลดเสียงล้มเหลว";
      case "completed": return "✓ เสร็จสิ้นคิวงานถอดความ";
      case "stopped": return "🛑 ระบบหยุดการทำงาน";
      default: return state || "รอดำเนินการ...";
    }
  };

  // Fetch stats and live status when tab changes to dashboard or videos load
  useEffect(() => {
    if (activeTab === "dashboard") {
      fetchStats();
      fetchTranscriptionStatus();
      
      const interval = setInterval(() => {
        fetchStats();
        fetchTranscriptionStatus();
      }, 5000);
      
      return () => clearInterval(interval);
    }
  }, [activeTab, videos]);

  // Debounce threshold updates to prevent lag during slider movement
  useEffect(() => {
    const timer = setTimeout(() => {
      setThreshold(localThreshold);
    }, 400);
    return () => clearTimeout(timer);
  }, [localThreshold]);

  // Auto-refresh search when threshold updates
  useEffect(() => {
    if (searchQuery.trim() && searchResults.length > 0) {
      handleSearch(undefined, searchQuery);
    }
  }, [threshold]);

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
      
      let data: any = {};
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        data = await response.json();
      } else {
        const text = await response.text();
        throw new Error(text || `HTTP error! Status: ${response.status}`);
      }
      
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
      
      let data: any = {};
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        data = await response.json();
      } else {
        const text = await response.text();
        throw new Error(text || `HTTP error! Status: ${response.status}`);
      }
      
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
      
      let data: any = {};
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        data = await response.json();
      } else {
        const text = await response.text();
        throw new Error(text || `HTTP error! Status: ${response.status}`);
      }
      
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
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    if (h > 0) {
      return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
    }
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

      {/* Tabs */}
      <div className="tabs-nav">
        <button
          type="button"
          className={`tab-btn ${activeTab === "search" ? "active" : ""}`}
          onClick={() => setActiveTab("search")}
        >
          🔍 ค้นหาในวิดีโอ
        </button>
        <button
          type="button"
          className={`tab-btn ${activeTab === "dashboard" ? "active" : ""}`}
          onClick={() => setActiveTab("dashboard")}
        >
          📊 ความคืบหน้าทำสคริปต์
        </button>
      </div>

      {activeTab === "search" ? (
        <>
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
                      <span>{localThreshold}%</span>
                    </div>
                    <input
                      type="range"
                      min="60"
                      max="100"
                      value={localThreshold}
                      onChange={(e) => setLocalThreshold(parseInt(e.target.value))}
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
                            type="button"
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
                        <span>🔍 YouTube พบว่าวิดีโอนี้น่าจะเกี่ยวข้อง แต่ยังไม่มีสคริปต์ในฐานข้อมูลของเรา</span>
                        <span style={{ fontSize: "0.8rem", color: "var(--t3)" }}>
                          คลิก "เปิดใน YouTube" เพื่อดูวิดีโอโดยตรง หรือรอสักครู่ในขณะที่เรากำลังเพิ่มสคริปต์ให้ครบ
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
                              <span className={`badge ${match.match_type}`}>
                                {match.match_type === "exact" && "ตรงเป๊ะ"}
                                {match.match_type === "partial" && "ตรงบางส่วน"}
                                {match.match_type === "fuzzy" && "ใกล้เคียง"}
                                {match.match_type === "estimated" && "คาดการณ์ตำแหน่ง"}
                                {match.match_type !== "exact" && match.match_type !== "partial" && match.match_type !== "fuzzy" && match.match_type !== "estimated" && match.match_type}
                                {" "}
                                ({Math.round(match.score)}%)
                              </span>
                              <span style={{ color: "var(--text-muted)" }}>•</span>
                              {match.match_type !== "estimated" ? (
                                <button
                                  type="button"
                                  className="copy-btn"
                                  onClick={() => handleCopyLink(result.video_id, match.start)}
                                >
                                  คัดลอกลิงก์พร้อมแถมเวลา
                                </button>
                              ) : (
                                <span style={{ color: "var(--t3)", fontSize: "0.75rem" }}>
                                  (กรุณากดเปิดเพื่อฟัง/ดูตำแหน่งจริง)
                                </span>
                              )}
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
        </>
      ) : (
        /* New Dashboard Panel */
        <div className="dashboard-container" style={{ animation: "slideIn 0.25s ease-out" }}>
          {/* Active Transcription Task Indicator */}
          {transcriptionStatus && (
            <div className={`live-status-card ${transcriptionStatus.status === "running" ? "active" : "idle"}`}>
              <div className="live-status-header">
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span className={`live-pulse-dot ${transcriptionStatus.status === "running" ? "running" : "idle"}`}></span>
                  <span style={{ fontWeight: "600", fontSize: "0.9rem" }}>
                    {transcriptionStatus.status === "running" ? "กำลังถอดความศาสนาอิสลามเบื้องหลัง (Live)" : "ระบบถอดความเบื้องหลัง: สแตนด์บาย"}
                  </span>
                </div>
                {transcriptionStatus.last_updated > 0 && (
                  <span style={{ fontSize: "0.75rem", color: "var(--t3)" }}>
                    อัปเดตล่าสุด: {new Date(transcriptionStatus.last_updated * 1000).toLocaleTimeString("th-TH")}
                  </span>
                )}
              </div>
              
              {transcriptionStatus.status === "running" ? (
                <div className="live-status-body">
                  <div className="live-video-info">
                    <span className="live-video-label">วิดีโอปัจจุบัน:</span>
                    <span className="live-video-title" title={transcriptionStatus.current_video_title}>
                      {transcriptionStatus.current_video_title || "ไม่ทราบชื่อคลิป"}
                    </span>
                  </div>
                  
                  <div className="live-progress-bar-wrapper">
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", marginBottom: "0.35rem" }}>
                      <span style={{ color: "var(--teal)", fontWeight: "500" }}>
                        {getProgressStateLabel(transcriptionStatus.progress_state)}
                      </span>
                      <span style={{ fontWeight: "600" }}>
                        คลิปที่ {transcriptionStatus.current_index}/{transcriptionStatus.total_to_process} ({Math.round((transcriptionStatus.current_index / transcriptionStatus.total_to_process) * 100)}%)
                      </span>
                    </div>
                    <div className="live-progress-bg">
                      <div 
                        className="live-progress-fill" 
                        style={{ width: `${(transcriptionStatus.current_index / transcriptionStatus.total_to_process) * 100}%` }}
                      ></div>
                    </div>
                  </div>
                  
                  <div className="live-stats-row">
                    <span>สำเร็จรอบนี้: <strong style={{ color: "var(--success)" }}>{transcriptionStatus.success_count}</strong></span>
                    <span>•</span>
                    <span>ล้มเหลวรอบนี้: <strong style={{ color: "var(--error)" }}>{transcriptionStatus.fail_count}</strong></span>
                  </div>
                </div>
              ) : (
                <div className="live-status-body idle">
                  <p style={{ fontSize: "0.85rem", color: "var(--t2)" }}>
                    ขณะนี้ไม่มีวิดีโอที่กำลังถอดความอยู่ ระบบพร้อมสำหรับเริ่มถอดความในคิวงานถัดไป
                  </p>
                  {transcriptionStatus.success_count > 0 && (
                    <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--t3)" }}>
                      ผลลัพธ์รอบล่าสุด: สำเร็จ {transcriptionStatus.success_count} คลิป, ล้มเหลว {transcriptionStatus.fail_count} คลิป
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Dashboard Stats */}
          <div className="dashboard-grid">
            <div className="stat-card">
              <span className="stat-label">วิดีโอทั้งหมด</span>
              <span className="stat-value">{videos.length} คลิป</span>
            </div>
            <div className="stat-card">
              <span className="stat-label">มีสคริปต์พร้อมค้นหาแล้ว</span>
              <span className="stat-value" style={{ color: "var(--success)" }}>
                {statsLoading ? "..." : `${stats?.transcribed_count || 0} คลิป`}
              </span>
            </div>
            <div className="stat-card">
              <span className="stat-label">รอคิวแกะเสียง</span>
              <span className="stat-value" style={{ color: "#f59e0b" }}>
                {statsLoading ? "..." : `${videos.length > 0 && stats ? Math.max(0, videos.length - stats.transcribed_count) : 0} คลิป`}
              </span>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="progress-container">
            <div className="progress-header">
              <span style={{ fontWeight: "500" }}>ความคืบหน้าการถอดความสคริปต์ของช่อง</span>
              <span style={{ fontWeight: "600", color: "var(--teal)" }}>
                {stats && videos.length > 0 ? `${((stats.transcribed_count / videos.length) * 100).toFixed(1)}%` : "0%"}
              </span>
            </div>
            <div className="progress-bg">
              <div
                className="progress-bar-fill"
                style={{
                  width: stats && videos.length > 0 ? `${(stats.transcribed_count / videos.length) * 100}%` : "0%"
                }}
              ></div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.75rem", fontSize: "0.8rem", color: "var(--t3)", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
              <span>ระบบถอดความเบื้องหลังกำลังทำงานโดยใช้ Gemini API...</span>
              <button
                type="button"
                className="copy-btn"
                style={{ color: "var(--acc)", textDecoration: "underline", fontWeight: "600" }}
                onClick={fetchStats}
                disabled={statsLoading}
              >
                🔄 {statsLoading ? "กำลังอัปเดต..." : "กดรีเฟรชเพื่ออัปเดตความคืบหน้า"}
              </button>
            </div>
          </div>

          {/* Video List Card */}
          <div className="dashboard-list-card">
            <div className="dashboard-list-header">
              <h3 style={{ fontSize: "1rem", fontWeight: "600", color: "var(--text)" }}>รายการวิดีโอและสถานะสคริปต์</h3>
              <input
                type="text"
                className="video-search-input"
                style={{ maxWidth: "250px", margin: 0 }}
                placeholder="ค้นหาชื่อวิดีโอ..."
                value={dashboardSearchText}
                onChange={(e) => setDashboardSearchText(e.target.value)}
              />
            </div>

            {/* Filter Pills */}
            <div className="filter-pills-row">
              <button 
                type="button" 
                className={`filter-pill ${filterType === "all" ? "active" : ""}`}
                onClick={() => setFilterType("all")}
              >
                ทั้งหมด ({videos.length})
              </button>
              <button 
                type="button" 
                className={`filter-pill ${filterType === "transcribed" ? "active" : ""}`}
                onClick={() => setFilterType("transcribed")}
              >
                ✓ มีสคริปต์แล้ว ({stats?.transcribed_count || 0})
              </button>
              <button 
                type="button" 
                className={`filter-pill ${filterType === "pending" ? "active" : ""}`}
                onClick={() => setFilterType("pending")}
              >
                ⏳ รอคิวแกะเสียง ({stats?.no_subtitle_count || 0})
              </button>
            </div>

            <div style={{ maxHeight: "500px", overflowY: "auto", paddingRight: "0.5rem" }}>
              {videos
                .filter((v) => {
                  const matchesSearch = v.title.toLowerCase().includes(dashboardSearchText.toLowerCase());
                  if (!matchesSearch) return false;
                  const isTranscribed = stats?.transcribed_ids?.includes(v.id);
                  if (filterType === "transcribed") return isTranscribed;
                  if (filterType === "pending") return !isTranscribed;
                  return true;
                })
                .map((video) => {
                  const isTranscribed = stats?.transcribed_ids?.includes(video.id);
                  const isProcessing = transcriptionStatus?.status === "running" && transcriptionStatus?.current_video_id === video.id;
                  return (
                    <div key={video.id} className={`video-list-row ${isProcessing ? "processing-active" : ""}`}>
                      <img src={video.thumbnail} alt={video.title} className="video-list-img" />
                      <div className="video-list-content">
                        <div className="video-list-title" title={video.title}>
                          {video.title}
                        </div>
                        <div className="video-list-meta">
                          <span>{video.published_at}</span>
                          <span>•</span>
                          <span>ID: {video.id}</span>
                          <span>•</span>
                          {isProcessing ? (
                            <span className="status-badge-inline processing">
                              ⚡ กำลังประมวลผล...
                            </span>
                          ) : (
                            <span className={`status-badge-inline ${isTranscribed ? "done" : "pending"}`}>
                              {isTranscribed ? "✓ มีสคริปต์แล้ว" : "⏳ รอคิวแกะเสียง"}
                            </span>
                          )}
                        </div>
                      </div>
                      <div>
                        {isTranscribed ? (
                          <button
                            type="button"
                            className="result-card-btn"
                            onClick={() => fetchFullTranscript(video.id)}
                          >
                            📖 ดูสคริปต์
                          </button>
                        ) : isProcessing ? (
                          <div className="processing-loader-inline" title="ระบบกำลังทำการถอดสคริปต์คลิปนี้">
                            ⚙️
                          </div>
                        ) : (
                          <button
                            type="button"
                            className="result-card-btn"
                            disabled
                            style={{ cursor: "not-allowed", opacity: 0.5 }}
                          >
                            ⏳ รอแกะเสียง
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        </div>
      )}

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
