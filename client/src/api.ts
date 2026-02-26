import type { Conversation, Message, SSEEvent } from './types';

const API_BASE = '/api';

export async function fetchConversations(): Promise<Conversation[]> {
  const res = await fetch(`${API_BASE}/conversations`);
  if (!res.ok) throw new Error('Failed to fetch conversations');
  return res.json();
}

export async function fetchConversation(
  id: string
): Promise<{ id: string; title: string; created_at: string; messages: Message[] }> {
  const res = await fetch(`${API_BASE}/conversations/${id}`);
  if (!res.ok) throw new Error('Failed to fetch conversation');
  return res.json();
}

export async function createConversation(): Promise<Conversation> {
  const res = await fetch(`${API_BASE}/conversations`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to create conversation');
  return res.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/conversations/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete conversation');
}

export async function streamChat(
  conversationId: string | undefined,
  message: string,
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const body: Record<string, string> = { message };
  if (conversationId) {
    body.conversation_id = conversationId;
  }

  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    const text = await response.text();
    onEvent({ type: 'error', content: text || 'Request failed' });
    return;
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('data: ')) {
        try {
          const data: SSEEvent = JSON.parse(trimmed.slice(6));
          onEvent(data);
        } catch {
          // skip malformed lines
        }
      }
    }
  }

  // Process any remaining buffer
  if (buffer.trim().startsWith('data: ')) {
    try {
      const data: SSEEvent = JSON.parse(buffer.trim().slice(6));
      onEvent(data);
    } catch {
      // skip
    }
  }
}
