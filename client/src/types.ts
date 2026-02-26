export interface Conversation {
  id: string;
  title: string;
  created_at: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface SSEToken {
  type: 'token';
  content: string;
}

export interface SSEThinking {
  type: 'thinking';
  content: string;
}

export interface SSEToolStatus {
  type: 'tool_status';
  content: string;
}

export interface SSEDone {
  type: 'done';
  conversation_id: string;
}

export interface SSEError {
  type: 'error';
  content: string;
}

export type SSEEvent = SSEToken | SSEThinking | SSEToolStatus | SSEDone | SSEError;
