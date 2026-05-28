import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';

import { aiApi } from '@/services/api';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

type ContextType = 'general' | 'group' | 'daily' | 'case' | 'person';

interface ChatItem {
    id: string;
    title: string;
    context_type: ContextType;
    context_id?: string | null;
    updated_at?: string | null;
}

interface ChatMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    created_at?: string | null;
}

const contextLabels: Record<ContextType | string, string> = {
    general: 'Загальний',
    group: 'Група',
    daily: 'Денний',
    case: 'Справа',
    person: 'Особа',
};

export default function AiPage() {
    const [status, setStatus] = useState({ available: false, provider: 'gemini', model: '', version: '', detail: '' });
    const [chats, setChats] = useState<ChatItem[]>([]);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [selectedChat, setSelectedChat] = useState<ChatItem | null>(null);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(true);
    const [sending, setSending] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [quickResult, setQuickResult] = useState<{ title: string; content: string; reportType: string; contextId?: string } | null>(null);
    const [draftAssistant, setDraftAssistant] = useState('');
    const [generating, setGenerating] = useState(false);
    const abortRef = useRef<AbortController | null>(null);
    const messagesEndRef = useRef<HTMLDivElement | null>(null);

    const token = localStorage.getItem('token') || '';

    const loadInitial = async () => {
        setLoading(true);
        try {
            const [statusRes, chatsRes] = await Promise.all([
                aiApi.status(),
                aiApi.chats(),
            ]);
            setStatus(statusRes.data);
            setChats(chatsRes.data);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося завантажити AI-модуль');
        } finally {
            setLoading(false);
        }
    };

    const loadChat = async (chat: ChatItem) => {
        setSelectedChat(chat);
        setQuickResult(null);
        setDraftAssistant('');
        setError('');
        try {
            const messagesRes = await aiApi.messages(chat.id);
            setMessages(messagesRes.data);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося завантажити чат');
        }
    };

    useEffect(() => {
        loadInitial();
    }, []);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, draftAssistant, selectedChat, quickResult]);

    const createGeneralChat = async (content: string) => {
        const res = await aiApi.createChat({
            context_type: 'general',
            first_message: content,
        });
        const chatsRes = await aiApi.chats();
        setChats(chatsRes.data);
        const created = chatsRes.data.find((item: ChatItem) => item.id === res.data.id) || {
            id: res.data.id,
            title: content.slice(0, 50),
            context_type: 'general' as ContextType,
        };
        setSelectedChat(created);
        setQuickResult(null);
        setMessages([]);
        return created;
    };

    const streamChatMessage = async (chat: ChatItem, content: string) => {
        setSending(true);
        setError('');
        setSuccess('');
        setMessages(prev => [
            ...prev,
            { id: `u-${Date.now()}`, role: 'user', content },
            { id: `a-${Date.now()}`, role: 'assistant', content: '' },
        ]);
        setDraftAssistant('');

        const controller = new AbortController();
        abortRef.current = controller;

        try {
            const response = await fetch(`${API_BASE}/api/ai/chats/${chat.id}/message`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ content }),
                signal: controller.signal,
            });

            if (!response.ok || !response.body) {
                const text = await response.text();
                throw new Error(text || 'AI stream failed');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let currentDraft = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                while (buffer.includes('\n\n')) {
                    const boundary = buffer.indexOf('\n\n');
                    const rawEvent = buffer.slice(0, boundary);
                    buffer = buffer.slice(boundary + 2);

                    const line = rawEvent
                        .split('\n')
                        .find(part => part.startsWith('data: '));

                    if (!line) continue;
                    const payload = line.slice(6);
                    if (payload === '[DONE]') {
                        break;
                    }

                    let chunk = payload;
                    try {
                        chunk = JSON.parse(payload);
                    } catch {
                        chunk = payload;
                    }

                    if (typeof chunk === 'string' && !chunk.startsWith('[ERROR]')) {
                        currentDraft += chunk;
                        setDraftAssistant(currentDraft);
                    } else if (typeof chunk === 'string' && chunk.startsWith('[ERROR]')) {
                        throw new Error(chunk.replace('[ERROR] ', ''));
                    }
                }
            }

            const [messagesRes, chatsRes] = await Promise.all([
                aiApi.messages(chat.id),
                aiApi.chats(),
            ]);
            setMessages(messagesRes.data);
            setChats(chatsRes.data);
        } catch (err: any) {
            if (err.name !== 'AbortError') {
                setError(err.message || 'Не вдалося завершити генерацію');
            }
            const messagesRes = await aiApi.messages(chat.id).catch(() => null);
            if (messagesRes) {
                setMessages(messagesRes.data);
            }
        } finally {
            setSending(false);
            setDraftAssistant('');
            abortRef.current = null;
        }
    };

    const handleSend = async () => {
        const content = input.trim();
        if (!content || sending) return;
        setInput('');

        try {
            const chat = selectedChat || await createGeneralChat(content);
            await streamChatMessage(chat, content);
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Не вдалося створити чат');
        }
    };

    const handleStartNew = () => {
        abortRef.current?.abort();
        setSelectedChat(null);
        setQuickResult(null);
        setMessages([]);
        setDraftAssistant('');
        setInput('');
        setError('');
        setSuccess('');
    };

    const handleQuickDaily = async () => {
        setError('');
        setSuccess('');
        setGenerating(true);
        abortRef.current?.abort();
        try {
            const res = await aiApi.quickDaily();
            setSelectedChat(null);
            setMessages([]);
            setQuickResult({
                title: 'Денний брифінг',
                content: res.data.content,
                reportType: 'daily',
            });
            setSuccess('Денний брифінг згенеровано.');
        } catch (err: any) {
            const detail = err.response?.data?.detail || err.message || 'Не вдалося згенерувати денний брифінг';
            setError(detail);
        } finally {
            setGenerating(false);
        }
    };

    const handleDeleteChat = async (chatId: string) => {
        if (!confirm('Видалити цей чат?')) return;
        try {
            await aiApi.deleteChat(chatId);
            if (selectedChat?.id === chatId) {
                handleStartNew();
            }
            const chatsRes = await aiApi.chats();
            setChats(chatsRes.data);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося видалити чат');
        }
    };

    const visibleMessages = messages.filter(message => message.content || message.role === 'user');
    const hasConversation = Boolean(selectedChat || quickResult || visibleMessages.length || draftAssistant);
    const title = selectedChat?.title || quickResult?.title || 'FaceWatch AI';
    const contextType = selectedChat?.context_type || quickResult?.reportType || 'general';

    return (
        <div className="ai-chat-shell animate-fade-in">
            <aside className="ai-sidebar glass-card">
                <div className="ai-sidebar-actions">
                    <button className="ai-new-chat-button" onClick={handleStartNew}>Новий чат</button>
                    <button className="ai-brief-button" onClick={handleQuickDaily} disabled={generating}>
                        {generating ? 'Генерація...' : 'Денний брифінг'}
                    </button>
                </div>

                <div className="ai-chat-history">
                    <div className="ai-sidebar-title">Чати</div>
                    {chats.map(chat => (
                        <button
                            key={chat.id}
                            className={`ai-history-item ${selectedChat?.id === chat.id ? 'is-active' : ''}`}
                            onClick={() => loadChat(chat)}
                        >
                            <span className="ai-history-main">
                                <span className="ai-history-title">{chat.title}</span>
                                <span className="ai-history-meta">
                                    {contextLabels[chat.context_type] || chat.context_type}
                                    {chat.updated_at ? ` · ${new Date(chat.updated_at).toLocaleDateString('uk-UA')}` : ''}
                                </span>
                            </span>
                            <span
                                className="ai-history-delete"
                                role="button"
                                tabIndex={0}
                                onClick={(event) => {
                                    event.stopPropagation();
                                    handleDeleteChat(chat.id);
                                }}
                                onKeyDown={(event) => {
                                    if (event.key === 'Enter' || event.key === ' ') {
                                        event.preventDefault();
                                        event.stopPropagation();
                                        handleDeleteChat(chat.id);
                                    }
                                }}
                            >
                                ×
                            </span>
                        </button>
                    ))}
                    {!loading && chats.length === 0 && (
                        <div className="ai-empty-history">Чатів поки немає</div>
                    )}
                </div>

                <div className="ai-model-status">
                    <span className={`ai-status-dot ${status.available ? 'is-online' : ''}`} />
                    <div>
                        <div className="ai-status-title">{status.available ? status.model : 'Gemini не налаштований'}</div>
                        <div className="ai-status-subtitle">{status.available ? `Версія ${status.version || 'api'}` : status.detail || 'Немає з’єднання'}</div>
                    </div>
                </div>
            </aside>

            <main className="ai-chat-main glass-card">
                <header className="ai-chat-header">
                    <div>
                        <div className="ai-chat-title">{title}</div>
                        <div className="ai-chat-subtitle">{contextLabels[contextType] || contextType}</div>
                    </div>
                    <div className="ai-chat-header-spacer" />
                </header>

                {(error || success) && (
                    <div className={`ai-notice ${error ? 'is-error' : 'is-success'}`}>
                        {error || success}
                    </div>
                )}

                <section className={hasConversation ? 'ai-message-list' : 'ai-empty-chat'}>
                    {!hasConversation && (
                        <>
                            <div className="ai-empty-mark">FW</div>
                            <h1>Чим допомогти?</h1>
                        </>
                    )}

                    {quickResult && (
                        <article className="ai-message-row assistant">
                            <div className="ai-avatar">AI</div>
                            <div className="ai-message ai-message-assistant ai-assistant-content">
                                <ReactMarkdown>{quickResult.content}</ReactMarkdown>
                            </div>
                        </article>
                    )}

                    {visibleMessages.map(message => (
                        <article key={message.id} className={`ai-message-row ${message.role}`}>
                            {message.role === 'assistant' && <div className="ai-avatar">AI</div>}
                            <div className={`ai-message ${message.role === 'user' ? 'ai-message-user' : 'ai-message-assistant ai-assistant-content'}`}>
                                {message.role === 'assistant'
                                    ? <ReactMarkdown>{message.content}</ReactMarkdown>
                                    : <div>{message.content}</div>}
                            </div>
                        </article>
                    ))}

                    {draftAssistant && (
                        <article className="ai-message-row assistant">
                            <div className="ai-avatar">AI</div>
                            <div className="ai-message ai-message-assistant ai-assistant-content">
                                <ReactMarkdown>{draftAssistant}</ReactMarkdown>
                            </div>
                        </article>
                    )}

                    {sending && !draftAssistant && (
                        <article className="ai-message-row assistant">
                            <div className="ai-avatar">AI</div>
                            <div className="ai-thinking">Пише відповідь...</div>
                        </article>
                    )}
                    <div ref={messagesEndRef} />
                </section>

                <footer className="ai-composer">
                    <textarea
                        className="ai-composer-input"
                        value={input}
                        onChange={(event) => setInput(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === 'Enter' && !event.shiftKey) {
                                event.preventDefault();
                                handleSend();
                            }
                        }}
                        placeholder="Напишіть повідомлення"
                        disabled={sending}
                    />
                    <div className="ai-composer-actions">
                        {sending && (
                            <button className="ai-stop-button" onClick={() => abortRef.current?.abort()}>
                                Стоп
                            </button>
                        )}
                        <button className="ai-send-button" onClick={handleSend} disabled={sending || !input.trim()}>
                            Надіслати
                        </button>
                    </div>
                </footer>
            </main>
        </div>
    );
}
