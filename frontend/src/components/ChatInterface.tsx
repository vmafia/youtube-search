import React, { useState, useRef, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || 
  (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
    ? "http://localhost:5000"
    : "");

export function ChatInterface() {
  const [messages, setMessages] = useState<{role: 'user'|'assistant'|'system', content: string, context?: any[]}[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = { role: 'user' as const, content: input.trim() };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      // Create message history payload (excluding context to save bandwidth)
      const messageHistory = [...messages, userMessage].map(m => ({ role: m.role, content: m.content }));
      
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: messageHistory })
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.error || "เกิดข้อผิดพลาดในการเชื่อมต่อกับ AI");
      }
      
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response,
        context: data.context_used
      }]);
      
    } catch (err: any) {
      setMessages(prev => [...prev, {
        role: 'system',
        content: `Error: ${err.message}`
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-container">
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
              <div className="chat-bubble">
                {msg.content}
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
        
        {loading && (
          <div className="chat-message assistant">
            <div className="chat-message-avatar">🤖</div>
            <div className="chat-message-content">
              <div className="chat-bubble typing">
                <span className="dot"></span>
                <span className="dot"></span>
                <span className="dot"></span>
              </div>
            </div>
          </div>
        )}
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
