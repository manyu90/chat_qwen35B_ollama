import { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import type { Conversation } from './types';
import {
  fetchConversations,
  deleteConversation,
} from './api';

function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Load conversations on mount
  useEffect(() => {
    loadConversations();
  }, []);

  const loadConversations = async () => {
    try {
      const convs = await fetchConversations();
      setConversations(convs);
    } catch {
      // Server might not be running yet
    }
  };

  const handleNewChat = useCallback(() => {
    setActiveConversationId(null);
  }, []);

  const handleSelectConversation = useCallback((id: string) => {
    setActiveConversationId(id);
  }, []);

  const handleDeleteConversation = useCallback(
    async (id: string) => {
      try {
        await deleteConversation(id);
        setConversations((prev) => prev.filter((c) => c.id !== id));
        if (activeConversationId === id) {
          setActiveConversationId(null);
        }
      } catch {
        // ignore
      }
    },
    [activeConversationId]
  );

  const handleConversationCreated = useCallback((newId: string) => {
    setActiveConversationId(newId);
    // Reload conversations to get the new one with its title
    loadConversations();
  }, []);

  return (
    <div className="app">
      <button
        className="sidebar-toggle"
        onClick={() => setSidebarOpen(!sidebarOpen)}
        aria-label="Toggle sidebar"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <path
            d="M3 5h14M3 10h14M3 15h14"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
      </button>

      <div className={`sidebar-wrapper ${sidebarOpen ? 'open' : 'closed'}`}>
        <Sidebar
          conversations={conversations}
          activeId={activeConversationId}
          onSelect={handleSelectConversation}
          onNew={handleNewChat}
          onDelete={handleDeleteConversation}
        />
      </div>

      <ChatArea
        conversationId={activeConversationId}
        onConversationCreated={handleConversationCreated}
      />
    </div>
  );
}

export default App;
