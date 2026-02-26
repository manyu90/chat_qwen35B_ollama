import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';

interface MessageProps {
  role: string;
  content: string;
  isStreaming?: boolean;
}

export default function Message({ role, content, isStreaming }: MessageProps) {
  const isUser = role === 'user';

  return (
    <div className={`message-row ${isUser ? 'message-user' : 'message-assistant'}`}>
      <div className="message-container">
        <div className="message-avatar">
          {isUser ? (
            <div className="avatar avatar-user">U</div>
          ) : (
            <div className="avatar avatar-assistant">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"
                  fill="#19C37D"
                />
              </svg>
            </div>
          )}
        </div>
        <div className="message-content">
          {isUser ? (
            <p>{content}</p>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight]}
              components={{
                pre({ children, ...props }) {
                  return (
                    <pre className="code-block" {...props}>
                      {children}
                    </pre>
                  );
                },
                code({ children, className, ...props }) {
                  const isInline = !className;
                  if (isInline) {
                    return (
                      <code className="inline-code" {...props}>
                        {children}
                      </code>
                    );
                  }
                  return (
                    <code className={className} {...props}>
                      {children}
                    </code>
                  );
                },
              }}
            >
              {content}
            </ReactMarkdown>
          )}
          {isStreaming && <span className="cursor-blink">|</span>}
        </div>
      </div>
    </div>
  );
}
