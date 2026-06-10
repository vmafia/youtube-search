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


export function App() {
  const [step, setStep] = useState<number>(1);
  const [channelName, setChannelName] = useState<string>("@AssabiqoonPublisher");
  const [videos, setVideos] = useState<Video[]>([]);
  const [selectedVideoIds, setSelectedVideoIds] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [threshold, setThreshold] = useState<number>(80);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  
  // Storage for latest 10 search queries
  const [searchHistory, setSearchHistory] = useLocalStorage<string[]>("search_history", []);
  
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Detailed transcript viewer state
  const [activeTranscriptVideoId, setActiveTranscriptVideoId] = useState<string | null>(null);
  const [fullTranscript, setFullTranscript] = useState<{ text: string; start: number; timestamp: string }[]>([]);
  const [transcriptLoading, setTranscriptLoading] = useState<boolean>(false);

  const addToast = (message: string, type: "success" | "error" = "success") => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  };

  const handleFetchVideos = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!channelName.trim()) {
      setError("กรุณากรอกชื่อช่องหรือ URL ของช่อง YouTube");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/channel-videos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel_name: channelName.trim() }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "ไม่สามารถดึงข้อมูลวิดีโอได้");
      }
      setVideos(data.videos || []);
      // By default select all videos
      setSelectedVideoIds((data.videos || []).map((v: Video) => v.id));
      addToast(`โหลดวิดีโอเสร็จสิ้น ${data.videos.length} รายการ`, "success");
      setStep(2);
    } catch (err: any) {
      setError(err.message || "เกิดข้อผิดพลาดในการดึงข้อมูล");
      addToast("การโหลดวิดีโอล้มเหลว", "error");
    } finally {
      setLoading(false);
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
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "เกิดข้อผิดพลาดในการค้นหา");
      }
      setSearchResults(data.results || []);
      
      // Update history
      const nextHistory = [
        queryToUse.trim(),
        ...searchHistory.filter((q) => q !== queryToUse.trim()),
      ].slice(0, 10);
      setSearchHistory(nextHistory);
      
      addToast(`ค้นหาเสร็จสิ้น พบผลลัพธ์ใน ${data.results.length} วิดีโอ`, "success");
    } catch (err: any) {
      setError(err.message || "เกิดข้อผิดพลาดในการส่งคำค้นหา");
      addToast("การค้นหาล้มเหลว", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleSelectAllVideos = () => {
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
      if (!response.ok) throw new Error(data.error || "ไม่สามารถดึง Transcript ได้");
      
      // Map start and duration
      const formatted = (data.transcript || []).map((t: any) => {
        const start = floatVal(t.start);
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

  const floatVal = (v: any): number => {
    const parsed = parseFloat(v);
    return isNaN(parsed) ? 0 : parsed;
  };

  const formatSeconds = (seconds: number): string => {
    const secs = Math.floor(seconds);
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div className="container">
      {/* Toast container */}
      <div className="toast-container">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.type}`}>
            {toast.message}
          </div>
        ))}
      </div>

      {/* Header */}
      <header style={{ textAlign: "center", marginBottom: "3rem" }}>
        <h1 style={{ fontSize: "2.5rem", fontWeight: "700", marginBottom: "0.5rem", background: "linear-gradient(135deg, #3b82f6, #8b5cf6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
          YouTube Transcript Search
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "1.1rem" }}>
          ค้นหาประโยคหรือคำพูดที่ต้องการจากวิดีโอในช่อง YouTube ได้อย่างแม่นยำ
        </p>
      </header>

      {/* Wizard Steps indicator */}
      <div style={{ maxWidth: "600px", margin: "0 auto 3rem auto" }}>
        <div className="wizard-header">
          <div className={`wizard-step ${step >= 1 ? "completed" : ""} ${step === 1 ? "active" : ""}`}>1</div>
          <div className={`wizard-step ${step >= 2 ? "completed" : ""} ${step === 2 ? "active" : ""}`}>2</div>
          <div className={`wizard-step ${step >= 3 ? "completed" : ""} ${step === 3 ? "active" : ""}`}>3</div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.9rem", color: "var(--text-secondary)", marginTop: "-1rem" }}>
          <span>เลือกช่อง YouTube</span>
          <span>เลือกวิดีโอ ({selectedVideoIds.length}/{videos.length})</span>
          <span>ค้นหาข้อความ</span>
        </div>
      </div>

      {/* Main card */}
      <main className="card" style={{ maxWidth: "1000px", margin: "0 auto" }}>
        {error && (
          <div style={{ background: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--error)", padding: "1rem", borderRadius: "8px", color: "var(--error)", marginBottom: "1.5rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>{error}</span>
            <button className="btn btn-secondary" onClick={() => setError(null)} style={{ padding: "0.3rem 0.6rem", fontSize: "0.8rem" }}>ปิด</button>
          </div>
        )}

        {/* STEP 1: SELECT CHANNEL */}
        {step === 1 && (
          <form onSubmit={handleFetchVideos}>
            <div className="form-group">
              <label className="form-label">ชื่อช่องหรือ URL ช่อง YouTube</label>
              <input
                type="text"
                className="form-input"
                placeholder="เช่น @AssabiqoonPublisher หรือ https://www.youtube.com/@AssabiqoonPublisher"
                value={channelName}
                onChange={(e) => setChannelName(e.target.value)}
              />
            </div>

            <div style={{ marginBottom: "2rem" }}>
              <span className="form-label" style={{ marginBottom: "0.5rem" }}>แนะนำ:</span>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: "0.9rem", padding: "0.5rem 1rem" }}
                onClick={() => setChannelName("@AssabiqoonPublisher")}
              >
                @AssabiqoonPublisher (ช่องที่เจาะจง)
              </button>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? "กำลังโหลด..." : "ดึงวิดีโอจากช่อง ->"}
              </button>
            </div>
          </form>
        )}

        {/* STEP 2: SELECT VIDEOS */}
        {step === 2 && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
              <div>
                <h2>เลือกวิดีโอที่จะค้นหา</h2>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem" }}>เลือกวิดีโอที่เกี่ยวข้องเพื่อเพิ่มความรวดเร็วในการค้นหา</p>
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button className="btn btn-secondary" onClick={handleSelectAllVideos}>
                  {selectedVideoIds.length === videos.length ? "ไม่เลือกเลย" : "เลือกทั้งหมด"}
                </button>
              </div>
            </div>

            <div className="video-grid">
              {videos.map((video) => (
                <div
                  key={video.id}
                  className={`video-card ${selectedVideoIds.includes(video.id) ? "selected" : ""}`}
                  onClick={() => toggleVideoSelection(video.id)}
                >
                  <img src={video.thumbnail} alt={video.title} className="video-thumbnail" />
                  <div className="video-info">
                    <h4 className="video-title">{video.title}</h4>
                    <div className="video-date">{video.published_at}</div>
                  </div>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "2rem" }}>
              <button className="btn btn-secondary" onClick={() => setStep(1)}>
                &lt;- ย้อนกลับ
              </button>
              <button
                className="btn btn-primary"
                onClick={() => setStep(3)}
                disabled={selectedVideoIds.length === 0}
              >
                ขั้นตอนต่อไป (ค้นหา) -&gt;
              </button>
            </div>
          </div>
        )}

        {/* STEP 3: SEARCH TRANSCRIPTS */}
        {step === 3 && (
          <div>
            <form onSubmit={handleSearch} style={{ marginBottom: "2rem" }}>
              <div className="form-group">
                <label className="form-label">คำค้นหา (ประโยค/วลี ทั้งภาษาไทยและภาษาอังกฤษ)</label>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="เช่น ทางรอดเดียว, holding fast"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                  <button type="submit" className="btn btn-primary" disabled={loading}>
                    {loading ? "กำลังค้นหา..." : "ค้นหา"}
                  </button>
                </div>
              </div>

              {/* Advanced Settings */}
              <div style={{ background: "rgba(255, 255, 255, 0.02)", padding: "1rem", borderRadius: "8px", border: "1px solid var(--border-glass)", marginBottom: "1rem" }}>
                <label className="form-label" style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Fuzzy Search Similarity Threshold: {threshold}%</span>
                  <span>(ค่าความคล้ายคลึงยอมรับคำสะกดผิด)</span>
                </label>
                <input
                  type="range"
                  min="60"
                  max="100"
                  value={threshold}
                  onChange={(e) => setThreshold(parseInt(e.target.value))}
                  style={{ width: "100%", accentColor: "var(--accent-blue)" }}
                />
              </div>

              {/* History */}
              {searchHistory.length > 0 && (
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
                  <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>ประวัติการค้นหา:</span>
                  {searchHistory.map((h, i) => (
                    <button
                      key={i}
                      type="button"
                      className="btn btn-secondary"
                      style={{ padding: "0.3rem 0.6rem", fontSize: "0.8rem" }}
                      onClick={() => {
                        setSearchQuery(h);
                        handleSearch(undefined, h);
                      }}
                    >
                      {h}
                    </button>
                  ))}
                </div>
              )}
            </form>

            <hr style={{ border: "0", height: "1px", background: "var(--border-glass)", margin: "2rem 0" }} />

            <div>
              <h3>ผลการค้นหา</h3>
              {searchResults.length === 0 ? (
                <p style={{ color: "var(--text-secondary)", marginTop: "1rem", textAlign: "center" }}>ไม่พบข้อมูลคำพูดในระบบ กรุณาลองใช้คำอื่นหรือลดระดับความคล้ายคลึงลง</p>
              ) : (
                <div className="results-list">
                  {searchResults.map((result) => {
                    const videoInfo = videos.find((v) => v.id === result.video_id);
                    return (
                      <div key={result.video_id} style={{ background: "rgba(255, 255, 255, 0.02)", border: "1px solid var(--border-glass)", borderRadius: "12px", padding: "1.5rem", marginBottom: "1.5rem" }}>
                        <div style={{ display: "flex", gap: "1rem", marginBottom: "1rem", flexWrap: "wrap" }}>
                          {videoInfo && (
                            <>
                              <img src={videoInfo.thumbnail} alt={videoInfo.title} style={{ width: "140px", aspectRatio: "16/9", objectFit: "cover", borderRadius: "8px" }} />
                              <div style={{ flex: 1, minWidth: "200px" }}>
                                <h4 style={{ fontSize: "1.1rem", fontWeight: "600", marginBottom: "0.5rem" }}>{videoInfo.title}</h4>
                                <div style={{ display: "flex", gap: "0.5rem" }}>
                                  <button className="btn btn-secondary" style={{ fontSize: "0.8rem", padding: "0.3rem 0.7rem" }} onClick={() => fetchFullTranscript(result.video_id)}>
                                    ดู Transcript เต็ม
                                  </button>
                                  <a href={`https://youtu.be/${result.video_id}`} target="_blank" rel="noopener noreferrer" className="btn btn-secondary" style={{ fontSize: "0.8rem", padding: "0.3rem 0.7rem", textDecoration: "none" }}>
                                    เปิดคลิป YouTube
                                  </a>
                                </div>
                              </div>
                            </>
                          )}
                        </div>

                        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                          {result.matches.map((match, idx) => (
                            <div key={idx} className="result-item">
                              <div className="result-header">
                                <a
                                  href={`https://youtu.be/${result.video_id}?t=${Math.floor(match.start)}`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="result-timestamp"
                                >
                                  ⏰ {match.timestamp}
                                </a>
                                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                                  <span className={`badge badge-${match.match_type}`}>
                                    {match.match_type} {match.score < 100 && `(${match.score}%)`}
                                  </span>
                                  <button className="btn btn-secondary" style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }} onClick={() => handleCopyLink(result.video_id, match.start)}>
                                    Copy Link
                                  </button>
                                </div>
                              </div>
                              <p style={{ fontSize: "0.95rem", lineHeight: "1.5" }}>"{match.text}"</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "2rem" }}>
              <button className="btn btn-secondary" onClick={() => setStep(2)}>
                &lt;- ย้อนกลับ
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Transcript Modal Overlay */}
      {activeTranscriptVideoId && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0, 0, 0, 0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 2000, padding: "2rem" }}>
          <div className="card" style={{ width: "100%", maxWidth: "700px", maxHeight: "80vh", overflow: "hidden", display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
              <h3>Transcript ฉบับเต็ม</h3>
              <button className="btn btn-secondary" onClick={() => setActiveTranscriptVideoId(null)}>ปิด</button>
            </div>
            
            <div style={{ flex: 1, overflowY: "auto", paddingRight: "0.5rem" }}>
              {transcriptLoading ? (
                <p style={{ textAlign: "center", padding: "2rem" }}>กำลังดึงข้อมูล...</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  {fullTranscript.map((line, idx) => (
                    <div key={idx} style={{ display: "flex", gap: "1rem", alignItems: "flex-start", padding: "0.5rem", borderRadius: "6px", background: "rgba(255, 255, 255, 0.01)" }}>
                      <a
                        href={`https://youtu.be/${activeTranscriptVideoId}?t=${Math.floor(line.start)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontFamily: "monospace", color: "var(--accent-blue)", fontSize: "0.9rem", textDecoration: "none", fontWeight: "600", marginTop: "2px" }}
                      >
                        [{line.timestamp}]
                      </a>
                      <p style={{ fontSize: "0.95rem", flex: 1 }}>{line.text}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
export default App;
