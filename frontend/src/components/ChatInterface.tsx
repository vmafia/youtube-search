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

interface ChatInterfaceProps {
  videos?: Video[];
}

export function ChatInterface({ videos = [] }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>(() => {
    // Load from localStorage on mount
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("chat_history");
      if (saved) {
        try { return JSON.parse(saved); } catch (e) {}
      }
    }
    return [];
  });
  
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Save to localStorage whenever messages change
  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem("chat_history", JSON.stringify(messages));
    }
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = { role: 'user' as const, content: input.trim() };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    
    // Add an empty assistant message to stream into
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    try {
      const messageHistory = [...messages, userMessage].map(m => ({ role: m.role, content: m.content }));
      
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: messageHistory })
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
      
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          // The last element is either empty (ended in \n) or a partial line
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
                  setMessages(prev => {
                    const newMsgs = [...prev];
                    newMsgs[newMsgs.length - 1].context = data.context_used;
                    return newMsgs;
                  });
                } else if (data.type === 'status') {
                  setMessages(prev => {
                    const newMsgs = [...prev];
                    const lastMsg = newMsgs[newMsgs.length - 1];
                    lastMsg.content = `⏳ ${data.message}`;
                    return newMsgs;
                  });
                } else if (data.type === 'chunk') {
                  assistantText += data.content;
                  setMessages(prev => {
                    const newMsgs = [...prev];
                    const lastMsg = newMsgs[newMsgs.length - 1];
                    if (lastMsg.content.startsWith('⏳')) {
                      lastMsg.content = ''; // Clear the status message
                    }
                    lastMsg.content += data.content;
                    return newMsgs;
                  });
                }
              } catch (err) {
                // Ignore incomplete JSON chunks or parse errors
              }
            }
          }
        }
        
        if (done) break;
      }

      // If the stream ended (e.g. Vercel timeout) and no text was received at all
      if (!assistantText) {
        setMessages(prev => {
          const newMsgs = [...prev];
          const lastMsg = newMsgs[newMsgs.length - 1];
          // Only show error if we haven't already shown a stream error
          if (!lastMsg.content) {
            lastMsg.content = "[ระบบขัดข้อง: เซิร์ฟเวอร์ใช้เวลาตอบกลับนานเกินไป (Timeout) หรือ AI ขัดข้อง กรุณาลองถามใหม่อีกครั้ง]";
          }
          return newMsgs;
        });
      }
      
    } catch (err: any) {
      setMessages(prev => {
        // Remove the empty assistant message if it failed before typing
        const msgs = [...prev];
        if (msgs[msgs.length - 1].content === '') {
            msgs.pop();
        }
        return [...msgs, {
          role: 'system',
          content: `Error: ${err.message}`
        }];
      });
    } finally {
      setLoading(false);
    }
  };

  const clearHistory = () => {
    if(confirm("คุณต้องการลบประวัติการสนทนาทั้งหมดหรือไม่?")) {
      setMessages([]);
      localStorage.removeItem("chat_history");
    }
  };

  return (
    <div className="chat-container">
      <div className="chat-header" style={{display: 'flex', justifyContent: 'space-between', padding: '10px 20px', borderBottom: '1px solid var(--border)', alignItems: 'center'}}>
        <h3 style={{margin: 0, fontSize: '1rem', color: 'var(--t1)'}}>AI แชทบอท</h3>
        {messages.length > 0 && (
          <button onClick={clearHistory} style={{background: 'transparent', border: '1px solid var(--border)', color: 'var(--t2)', padding: '5px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem'}}>
            ลบแชท
          </button>
        )}
      </div>
      <div className="chat-messages">
        {messages.length === 0 && (
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
                          style={{ display: 'flex', alignItems: 'center', gap: '10px', textDecoration: 'none', background: 'var(--bg2)', padding: '8px', borderRadius: '8px', border: '1px solid var(--border)' }}
                        >
                          <img 
                            src={videoData?.thumbnail || `https://i.ytimg.com/vi/${ref.video_id}/mqdefault.jpg`} 
                            alt={videoData?.title || "Video thumbnail"} 
                            style={{ width: '80px', height: '45px', objectFit: 'cover', borderRadius: '4px' }} 
                          />
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span style={{ color: 'var(--t1)', fontWeight: 500, fontSize: '0.9rem', display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                              {videoData?.title || `วิดีโอ ${ref.video_id}`}
                            </span>
                            <span style={{ color: 'var(--accent)', fontSize: '0.8rem' }}>
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
  );
}
