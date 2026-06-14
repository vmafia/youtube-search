import React, { useState, useRef, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || 
  (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
    ? "http://localhost:5000"
    : "");

export function ChatInterface() {
  const [messages, setMessages] = useState<{role: 'user'|'assistant'|'system', content: string, context?: any[]}[]>(() => {
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
      
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          const chunkStr = decoder.decode(value, { stream: true });
          const lines = chunkStr.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6).trim();
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
                } else if (data.type === 'chunk') {
                  assistantText += data.content;
                  setMessages(prev => {
                    const newMsgs = [...prev];
                    newMsgs[newMsgs.length - 1].content = assistantText;
                    return newMsgs;
                  });
                }
              } catch (err) {
                // Ignore incomplete JSON chunks or parse errors
              }
            }
          }
        }
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
                {msg.content || (loading && i === messages.length - 1 ? <span className="typing-indicator"><span className="dot"></span><span className="dot"></span><span className="dot"></span></span> : '')}
              </div>
              
              {/* Show referenced videos if AI used context */}
              {msg.context && msg.context.length > 0 && (
                <div className="chat-references">
                  <span className="ref-label">🔍 อ้างอิงจากคลิป:</span>
                  <div className="ref-links">
                    {msg.context.map((ref, idx) => (
                      <a 
                        key={idx} 
                        href={`https://youtu.be/${ref.video_id}`} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="ref-link"
                      >
                        🎥 วิดีโอ {ref.video_id}
                      </a>
                    ))}
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
