

export type MascotState = 'idle' | 'searching' | 'thinking' | 'typing' | 'error';

interface AiMascotProps {
  state: MascotState;
  message?: string;
}

export function AiMascot({ state, message }: AiMascotProps) {
  // Define messages and animations based on state
  let defaultMessage = '';
  let animationClass = '';

  switch (state) {
    case 'idle':
      defaultMessage = 'สวัสดีครับ! ผมคือผู้ช่วย AI ถามเรื่องศาสนามาได้เลยครับ';
      animationClass = 'mascot-float';
      break;
    case 'searching':
      defaultMessage = 'กำลังสแกนหาคลิปที่เกี่ยวข้อง...';
      animationClass = 'mascot-pulse';
      break;
    case 'thinking':
      defaultMessage = 'กำลังวิเคราะห์เนื้อหาเชิงลึก...';
      animationClass = 'mascot-bounce';
      break;
    case 'typing':
      defaultMessage = 'กำลังเรียบเรียงคำตอบ...';
      animationClass = 'mascot-type-bounce';
      break;
    case 'error':
      defaultMessage = 'เกิดข้อผิดพลาดในการเชื่อมต่อ...';
      animationClass = 'mascot-shake';
      break;
    default:
      defaultMessage = 'พร้อมให้บริการครับ!';
      animationClass = 'mascot-float';
  }

  const displayMessage = message || defaultMessage;

  return (
    <div className="ai-mascot-container">
      <div className={`ai-mascot-img-wrapper ${animationClass}`}>
        <img 
          src="/mascot.png" 
          alt="AI Mascot" 
          className="ai-mascot-img"
        />
        {/* Glowing aura effect */}
        <div className={`ai-mascot-aura aura-${state}`}></div>
      </div>
      
      <div className="ai-mascot-speech-bubble">
        <p>{displayMessage}</p>
        <div className="speech-arrow"></div>
      </div>
    </div>
  );
}
