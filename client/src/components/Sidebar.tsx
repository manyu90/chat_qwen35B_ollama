import type { Conversation } from '../types';

interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export default function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <button className="new-chat-button" onClick={onNew}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path
              d="M8 1v14M1 8h14"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          New chat
        </button>
      </div>
      <nav className="sidebar-conversations">
        {conversations.map((conv) => (
          <div
            key={conv.id}
            className={`conversation-item ${
              conv.id === activeId ? 'conversation-active' : ''
            }`}
            onClick={() => onSelect(conv.id)}
          >
            <svg
              className="conversation-icon"
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
            >
              <path
                d="M2 3h12M2 6.5h12M2 10h8"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
            <span className="conversation-title">{conv.title}</span>
            <button
              className="conversation-delete"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(conv.id);
              }}
              aria-label="Delete conversation"
            >
              &times;
            </button>
          </div>
        ))}
      </nav>
    </aside>
  );
}
