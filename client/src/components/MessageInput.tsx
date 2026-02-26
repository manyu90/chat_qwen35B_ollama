import { useState, useRef, useEffect, KeyboardEvent } from 'react';

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

export default function MessageInput({ onSend, disabled }: MessageInputProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height =
        Math.min(textareaRef.current.scrollHeight, 200) + 'px';
    }
  }, [text]);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="input-area">
      <div className="input-container">
        <textarea
          ref={textareaRef}
          className="input-textarea"
          placeholder="Send a message..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
        />
        <button
          className="send-button"
          onClick={handleSend}
          disabled={disabled || !text.trim()}
          aria-label="Send message"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path
              d="M1.5 1.5L14.5 8L1.5 14.5V9.5L10 8L1.5 6.5V1.5Z"
              fill="currentColor"
            />
          </svg>
        </button>
      </div>
      <p className="input-disclaimer">
        AI can make mistakes. Consider checking important information.
      </p>
    </div>
  );
}
