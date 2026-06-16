import React, { useState, useRef, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || 
  (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
    ? "http://localhost:5000"
    : "");

interface Video {
  id: string;
  title: string;
  published_at: string;
  thumbnail: string;
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  context?: any[];
}

interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
}

interface ChatInterfaceProps {
  videos?: Video[];
}

export function ChatInterface({ videos = [] }: ChatInterfaceProps) {
  // Load sessions from localStorage
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("chat_sessions");
      if (saved) {
        try { 
          const parsed = JSON.parse(saved);
          if (parsed && parsed.length > 0) return parsed;
        } catch (e) {}
      }
      
      // Fallback: Check if there's old chat_history to migrate
      const oldHistory = localStorage.getItem("chat_history");
      if (oldHistory) {
        try {
          const parsedOld = JSON.parse(oldHistory);
          if (parsedOld && parsedOld.length > 0) {
            return [{
              id: Date.now().toString(),
              title: "ห้องแชทเดิม",
              messages: parsedOld,
              updatedAt: Date.now()
            }];
          }
        } catch (e) {}
      }
    }
    // Default empty session
    return [{
      id: Date.now().toString(),
      title: "แชทใหม่",
      messages: [{ role: 'assistant', content: 'สวัสดีครับ! มีเรื่องศาสนาอิสลามอะไรที่คุณอยากรู้จากวิดีโอไหมครับ?' }],
      updatedAt: Date.now()
    }];
  });

  const [activeSessionId, setActiveSessionId] = useState<string>(sessions[0]?.id);
  
  const activeSession = sessions.find(s => s.id === activeSessionId) || sessions[0];
  const messages = activeSession ? activeSession.messages : [];

  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" ? window.innerWidth <= 768 : false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(typeof window !== "undefined" ? window.innerWidth > 768 : true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Handle window resize for responsive sidebar
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth <= 768;
      setIsMobile(mobile);
      if (mobile) {
        setIsSidebarOpen(false);
      } else {
        setIsSidebarOpen(true);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Save to localStorage whenever sessions change
  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem("chat_sessions", JSON.stringify(sessions));
    }
  }, [sessions]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const updateActiveSession = (newMessages: Message[], autoTitle?: string) => {
    setSessions(prev => prev.map(s => {
      if (s.id === activeSessionId) {
        return {
          ...s,
          messages: newMessages,
          title: autoTitle || s.title,
          updatedAt: Date.now()
        };
      }
      return s;
    }).sort((a, b) => b.updatedAt - a.updatedAt));
  };

  const createNewSession = () => {
    const newSession: ChatSession = {
      id: Date.now().toString(),
      title: "แชทใหม่",
      messages: [{ role: 'assistant', content: 'สวัสดีครับ! มีเรื่องศาสนาอิสลามอะไรที่คุณอยากรู้จากวิดีโอไหมครับ?' }],
      updatedAt: Date.now()
    };
    setSessions(prev => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
  };

  const deleteSession = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if(confirm("คุณต้องการลบห้องแชทนี้หรือไม่?")) {
      setSessions(prev => {
        const filtered = prev.filter(s => s.id !== id);
        if (filtered.length === 0) {
          const fresh: ChatSession = {
            id: Date.now().toString(),
            title: "แชทใหม่",
            messages: [{ role: 'assistant', content: 'สวัสดีครับ! มีเรื่องศาสนาอิสลามอะไรที่คุณอยากรู้จากวิดีโอไหมครับ?' }],
            updatedAt: Date.now()
          };
          setActiveSessionId(fresh.id);
          return [fresh];
        }
        if (activeSessionId === id) {
          setActiveSessionId(filtered[0].id);
        }
        return filtered;
      });
    }
  };

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage: Message = { role: 'user', content: input.trim() };
    const currentMessages: Message[] = [...messages, userMessage];
    
    // Auto-title if it's a new chat
    let newTitle = activeSession.title;
    if (activeSession.title === "แชทใหม่" && currentMessages.filter(m => m.role === 'user').length === 1) {
      newTitle = input.trim().substring(0, 30) + (input.length > 30 ? "..." : "");
    }
    
    updateActiveSession(currentMessages, newTitle);
    setInput('');
    setLoading(true);
    
    // Add empty assistant message
    const msgsWithLoading: Message[] = [...currentMessages, { role: 'assistant', content: '' }];
    updateActiveSession(msgsWithLoading);

    try {
      const messageHistory = currentMessages.map(m => ({ role: m.role, content: m.content }));
      
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          messages: messageHistory,
          videos: videos.map(v => ({ id: v.id, title: v.title }))
        })
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || "เกิดข้อผิดพลาดในการเชื่อมต่อกับ AI");
      }
      
      if (!response.body) throw new Error("No response body");
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let done = false;
      let assistantText = "";
      let buffer = "";
      let finalMsgs = [...msgsWithLoading];
      
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || "";
          
          for (const line of lines) {
            const trimmedLine = line.trim();
            if (trimmedLine.startsWith('data: ')) {
              const dataStr = trimmedLine.slice(6).trim();
              if (dataStr === '[DONE]') {
                done = true;
                break;
              }
              try {
                const data = JSON.parse(dataStr);
                if (data.type === 'context') {
                  finalMsgs[finalMsgs.length - 1].context = data.context_used;
                  updateActiveSession(finalMsgs);
                } else if (data.type === 'status') {
                  finalMsgs[finalMsgs.length - 1].content = `⏳ ${data.message}`;
                  updateActiveSession(finalMsgs);
                } else if (data.type === 'chunk') {
                  assistantText += data.content;
                  if (finalMsgs[finalMsgs.length - 1].content.startsWith('⏳')) {
                    finalMsgs[finalMsgs.length - 1].content = '';
                  }
                  finalMsgs[finalMsgs.length - 1].content = assistantText;
                  updateActiveSession(finalMsgs);
                }
              } catch (e) {
                console.error("Error parsing JSON chunk:", e, dataStr);
              }
            }
          }
        }
      }
    } catch (err: any) {
      const failedMsgs = [...msgsWithLoading];
      if (failedMsgs[failedMsgs.length - 1].content === '' || failedMsgs[failedMsgs.length - 1].content.startsWith('⏳')) {
          failedMsgs.pop();
      }
      failedMsgs.push({ role: 'system', content: `Error: ${err.message}` });
      updateActiveSession(failedMsgs);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-layout-wrapper" style={{ display: 'flex', height: 'calc(100vh - 200px)', minHeight: '500px', maxHeight: '800px', background: 'var(--bg2)', borderRadius: '12px', border: '1px solid var(--br)', overflow: 'hidden', position: 'relative' }}>
      
      {/* Sidebar Overlay Backdrop for Mobile */}
      {isSidebarOpen && isMobile && (
        <div 
          onClick={() => setIsSidebarOpen(false)}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.4)',
            backdropFilter: 'blur(2px)',
            zIndex: 9,
            transition: 'opacity 0.25s ease'
          }}
        />
      )}
      
      {/* Sidebar */}
      {isSidebarOpen && (
        <div className="chat-sidebar" style={{ width: '260px', minWidth: '260px', borderRight: '1px solid var(--br)', display: 'flex', flexDirection: 'column', background: 'var(--bg)', transition: 'all 0.3s ease', position: isMobile ? 'absolute' : 'relative', left: 0, top: 0, height: '100%', zIndex: 10 }}>
          <div style={{ padding: '15px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <button 
              onClick={createNewSession}
              style={{ flex: 1, padding: '10px', background: 'var(--acc)', color: '#000', border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
            >
              <span>+</span> แชทใหม่
            </button>
            {isMobile && (
              <button onClick={() => setIsSidebarOpen(false)} style={{ background: 'transparent', border: 'none', color: 'var(--text)', fontSize: '1.2rem', padding: '0 0 0 10px', cursor: 'pointer' }}>✕</button>
            )}
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '0 10px 10px 10px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
            {sessions.map(session => (
              <div 
                key={session.id}
                onClick={() => {
                  setActiveSessionId(session.id);
                  if (isMobile) setIsSidebarOpen(false);
                }}
                style={{
                  padding: '10px 12px',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  background: session.id === activeSessionId ? 'var(--bg3)' : 'transparent',
                  border: session.id === activeSessionId ? '1px solid var(--br)' : '1px solid transparent',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden' }}>
                  <span>💬</span>
                  <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: '0.9rem', color: session.id === activeSessionId ? 'var(--text)' : 'var(--t2)' }}>
                    {session.title}
                  </span>
                </div>
                <button 
                  onClick={(e) => deleteSession(e, session.id)}
                  style={{ background: 'transparent', border: 'none', color: 'var(--t3)', cursor: 'pointer', padding: '2px 5px', borderRadius: '4px' }}
                  title="ลบแชท"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main Chat Area */}
      <div className="chat-container" style={{ flex: 1, border: 'none', borderRadius: 0, height: '100%', maxHeight: 'none', minWidth: 0, transition: 'all 0.3s ease', display: 'flex', flexDirection: 'column' }}>
        <div className="chat-header" style={{display: 'flex', gap: '15px', padding: '15px 20px', borderBottom: '1px solid var(--br)', alignItems: 'center'}}>
          <button 
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            style={{ background: 'var(--bg2)', border: '1px solid var(--br)', color: 'var(--text)', fontSize: '1.1rem', cursor: 'pointer', padding: '4px 8px', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            title="ซ่อน/แสดงแถบห้องแชท"
          >
            {isSidebarOpen ? '◀' : '☰'}
          </button>
          <h3 style={{margin: 0, fontSize: '1rem', color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>{activeSession?.title || "AI แชทบอท"}</h3>
        </div>
        
        <div className="chat-messages" style={{ flex: 1, overflowY: 'auto' }}>
          {messages.length === 1 && messages[0].role === 'assistant' && (
            <div className="chat-empty">
              <div className="chat-empty-icon" style={{ fontSize: '3rem', marginBottom: '1rem' }}>🤖</div>
              <h3 style={{ marginBottom: '0.5rem' }}>AI ถาม-ตอบจากคลิป</h3>
              <p style={{ color: 'var(--t2)', fontSize: '0.95rem' }}>
                พิมพ์คำถามเกี่ยวกับเนื้อหาในวิดีโอ เช่น "อาจารย์พูดถึงเรื่องนบีปลอมว่ายังไงบ้าง?"
              </p>
            </div>
          )}
          
          {messages.map((msg, i) => (
            <div key={i} className={`chat-message ${msg.role}`}>
              <div className="chat-message-avatar">
                {msg.role === 'user' ? '🧑‍💻' : (msg.role === 'assistant' ? '🤖' : '⚠️')}
              </div>
              <div className="chat-message-content">
                <div className="chat-bubble" style={{ whiteSpace: 'pre-wrap' }}>
                  {msg.content === '' ? (
                    <span style={{ fontStyle: 'italic', color: '#888' }}>กำลังประมวลผล...</span>
                  ) : (
                    msg.content
                  )}
                </div>
                
                {/* Show referenced videos if AI used context */}
                {msg.context && msg.context.length > 0 && (
                  <div className="chat-references">
                    <span className="ref-label">🔍 อ้างอิงจากคลิป:</span>
                    <div className="ref-links" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {msg.context.map((ref, idx) => {
                        const videoData = videos.find(v => v.id === ref.video_id);
                        return (
                          <a 
                            key={idx} 
                            href={`https://youtu.be/${ref.video_id}`} 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="ref-link"
                            style={{ display: 'flex', alignItems: 'center', gap: '10px', textDecoration: 'none', background: 'var(--bg2)', padding: '8px', borderRadius: '8px', border: '1px solid var(--br)' }}
                          >
                            <img 
                              src={videoData?.thumbnail || `https://i.ytimg.com/vi/${ref.video_id}/mqdefault.jpg`} 
                              alt={videoData?.title || "Video thumbnail"} 
                              style={{ width: '80px', height: '45px', objectFit: 'cover', borderRadius: '4px' }} 
                            />
                            <div style={{ display: 'flex', flexDirection: 'column' }}>
                              <span style={{ color: 'var(--text)', fontWeight: 500, fontSize: '0.9rem', display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                                {videoData?.title || `วิดีโอ ${ref.video_id}`}
                              </span>
                              <span style={{ color: 'var(--acc)', fontSize: '0.8rem' }}>
                                ▶️ ดูคลิปเต็ม
                              </span>
                            </div>
                          </a>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
        
        <form className="chat-input-area" onSubmit={handleSend}>
          <input 
            type="text" 
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="พิมพ์คำถามของคุณที่นี่..."
            className="chat-input"
            disabled={loading}
          />
          <button type="submit" className="chat-send-btn" disabled={loading || !input.trim()}>
            ส่ง
          </button>
        </form>
      </div>
    </div>
  );
}
