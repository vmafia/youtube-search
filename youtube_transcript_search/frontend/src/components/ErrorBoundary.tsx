import React, { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error:", error, errorInfo);
  }

  public handleReload = () => {
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
          padding: '2rem',
          textAlign: 'center',
          background: '#0b0f19',
          color: '#f3f4f6'
        }}>
          <h1 style={{ marginBottom: '1rem', color: '#ef4444' }}>เกิดข้อผิดพลาดบางอย่าง</h1>
          <p style={{ color: '#9ca3af', marginBottom: '2rem', maxWidth: '500px' }}>
            แอปพลิเคชันหยุดทำงานเนื่องจากมีข้อผิดพลาดที่ไม่คาดคิด: {this.state.error?.message}
          </p>
          <button 
            onClick={this.handleReload}
            style={{
              padding: '0.8rem 1.5rem',
              background: '#3b82f6',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600
            }}
          >
            เริ่มแอปใหม่
          </button>
        </div>
      );
    }

    return this.children;
  }
}
export default ErrorBoundary;
