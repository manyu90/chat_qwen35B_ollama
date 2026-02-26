import { useState, useEffect, useRef, useCallback } from 'react';
import Message from './Message';
import MessageInput from './MessageInput';
import type { Message as MessageType, SSEEvent } from '../types';
import { streamChat, fetchConversation } from '../api';

interface ChatAreaProps {
  conversationId: string | null;
  onConversationCreated: (id: string) => void;
}

export default function ChatArea({
  conversationId,
  onConversationCreated,
}: ChatAreaProps) {
  const [messages, setMessages] = useState<MessageType[]>([]);
  const [streamingContent, setStreamingContent] = useState('');
  const [thinkingContent, setThinkingContent] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [toolStatus, setToolStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Load messages when conversation changes
  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const data = await fetchConversation(conversationId);
        if (!cancelled) {
          setMessages(data.messages);
        }
      } catch {
        if (!cancelled) {
          setMessages([]);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent, thinkingContent, isLoading]);

  const handleSend = useCallback(
    async (text: string) => {
      setError(null);
      setToolStatus(null);
      setThinkingContent('');
      setIsThinking(false);

      // Add user message to local state immediately
      const userMessage: MessageType = {
        id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        role: 'user',
        content: text,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);

      setIsLoading(true);
      setIsStreaming(true);
      setStreamingContent('');

      abortControllerRef.current = new AbortController();

      let currentConvId = conversationId;
      let gotFirstToken = false;

      try {
        await streamChat(
          currentConvId || undefined,
          text,
          (event: SSEEvent) => {
            switch (event.type) {
              case 'thinking':
                setIsLoading(false);
                setIsThinking(true);
                setThinkingContent((prev) => prev + event.content);
                break;

              case 'token':
                if (!gotFirstToken) {
                  gotFirstToken = true;
                  setIsLoading(false);
                  setIsThinking(false);
                }
                setStreamingContent((prev) => prev + event.content);
                break;

              case 'tool_status':
                setIsThinking(false);
                setToolStatus(event.content);
                break;

              case 'done':
                if (!currentConvId && event.conversation_id) {
                  currentConvId = event.conversation_id;
                  onConversationCreated(event.conversation_id);
                }
                break;

              case 'error':
                setError(event.content);
                break;
            }
          },
          abortControllerRef.current.signal
        );
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          // User cancelled
        } else {
          setError('Failed to send message. Is the server running?');
        }
      }

      // Finalize: reload messages from server to get proper IDs
      setStreamingContent('');
      setIsStreaming(false);
      setIsLoading(false);
      setIsThinking(false);
      setThinkingContent('');
      setToolStatus(null);
      abortControllerRef.current = null;

      // Reload conversation from DB to get all messages with real IDs
      const reloadId = currentConvId;
      if (reloadId) {
        try {
          const data = await fetchConversation(reloadId);
          setMessages(data.messages);
        } catch {
          // keep local state if reload fails
        }
      }
    },
    [conversationId, onConversationCreated]
  );

  // Show welcome state when no conversation selected
  if (!conversationId && messages.length === 0 && !isStreaming) {
    return (
      <main className="chat-area">
        <div className="welcome-container">
          <div className="welcome-icon">
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
              <circle cx="20" cy="20" r="18" stroke="#19C37D" strokeWidth="2" />
              <path
                d="M20 10c-5.52 0-10 4.48-10 10s4.48 10 10 10 10-4.48 10-10S25.52 10 20 10zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"
                fill="#19C37D"
              />
            </svg>
          </div>
          <h1 className="welcome-title">How can I help you today?</h1>
          <p className="welcome-subtitle">
            Start a conversation by typing a message below.
          </p>
        </div>
        <MessageInput onSend={handleSend} disabled={isStreaming} />
      </main>
    );
  }

  return (
    <main className="chat-area">
      <div className="messages-container">
        {messages.map((msg) => (
          <Message key={msg.id} role={msg.role} content={msg.content} />
        ))}

        {isLoading && !streamingContent && !isThinking && (
          <div className="message-row message-assistant">
            <div className="message-container">
              <div className="message-avatar">
                <div className="avatar avatar-assistant">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"
                      fill="#19C37D"
                    />
                  </svg>
                </div>
              </div>
              <div className="message-content">
                <div className="loading-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          </div>
        )}

        {isThinking && thinkingContent && (
          <div className="message-row message-assistant">
            <div className="message-container">
              <div className="message-avatar">
                <div className="avatar avatar-assistant">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"
                      fill="#19C37D"
                    />
                  </svg>
                </div>
              </div>
              <div className="message-content">
                <div className="thinking-block">
                  <div className="thinking-header">
                    <div className="thinking-spinner"></div>
                    <span>Thinking...</span>
                  </div>
                  <div className="thinking-text">{thinkingContent}</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {streamingContent && (
          <Message
            role="assistant"
            content={streamingContent}
            isStreaming={true}
          />
        )}

        {toolStatus && (
          <div className="tool-status">
            <div className="tool-status-spinner"></div>
            <span>{toolStatus}</span>
          </div>
        )}

        {error && (
          <div className="error-banner">
            <span>{error}</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <MessageInput onSend={handleSend} disabled={isStreaming} />
    </main>
  );
}
