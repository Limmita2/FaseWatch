import { FormEvent, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';

import { aiApi, groupsApi } from '@/services/api';

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

interface GroupOption {
    id: string;
    name: string;
}

export default function AiPage() {
    const [status, setStatus] = useState({ available: false, model: '', version: '' });
    const [chats, setChats] = useState<ChatItem[]>([]);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [groups, setGroups] = useState<GroupOption[]>([]);
    const [selectedChat, setSelectedChat] = useState<ChatItem | null>(null);
    const [summary, setSummary] = useState<any>(null);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(true);
    const [sending, setSending] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [showNewChat, setShowNewChat] = useState(false);
    const [showQuickModal, setShowQuickModal] = useState<'case' | 'person' | null>(null);
    const [quickResult, setQuickResult] = useState<{ title: string; content: string; reportType: string; contextId?: string } | null>(null);
    const [newChatForm, setNewChatForm] = useState({
        context_type: 'general' as ContextType,
        context_id: '',
        first_message: '',
    });
    const [quickInput, setQuickInput] = useState('');
    const [draftAssistant, setDraftAssistant] = useState('');
    const [generating, setGenerating] = useState(false);
    const abortRef = useRef<AbortController | null>(null);
    const messagesEndRef = useRef<HTMLDivElement | null>(null);

    const token = localStorage.getItem('token') || '';

    const loadInitial = async () => {
        setLoading(true);
        try {
            const [statusRes, chatsRes, groupsRes] = await Promise.all([
                aiApi.status(),
                aiApi.chats(),
                groupsApi.list(),
            ]);
            setStatus(statusRes.data);
            setChats(chatsRes.data);
            setGroups(groupsRes.data);
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
        try {
            const [messagesRes, summaryRes] = await Promise.all([
                aiApi.messages(chat.id),
                aiApi.summary(chat.id),
            ]);
            setMessages(messagesRes.data);
            setSummary(summaryRes.data.summary);
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

            const [messagesRes, chatsRes, summaryRes] = await Promise.all([
                aiApi.messages(chat.id),
                aiApi.chats(),
                aiApi.summary(chat.id),
            ]);
            setMessages(messagesRes.data);
            setChats(chatsRes.data);
            setSummary(summaryRes.data.summary);
            setSuccess('Відповідь отримано.');
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

    const handleCreateChat = async (e: FormEvent) => {
        e.preventDefault();
        const firstMessage = newChatForm.first_message.trim();
        try {
            const res = await aiApi.createChat({
                context_type: newChatForm.context_type,
                context_id: newChatForm.context_id || undefined,
                first_message: firstMessage,
            });
            const chatsRes = await aiApi.chats();
            setChats(chatsRes.data);
            const created = chatsRes.data.find((item: ChatItem) => item.id === res.data.id) || {
                id: res.data.id,
                title: firstMessage.slice(0, 50),
                context_type: newChatForm.context_type,
                context_id: newChatForm.context_id || undefined,
            };
            setShowNewChat(false);
            setNewChatForm({ context_type: 'general', context_id: '', first_message: '' });
            await loadChat(created);
            await streamChatMessage(created, firstMessage);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося створити чат');
        }
    };

    const handleSend = async () => {
        if (!selectedChat || !input.trim() || sending) return;
        const content = input.trim();
        setInput('');
        await streamChatMessage(selectedChat, content);
    };

    const handleQuickDaily = async () => {
        console.log('[AI] handleQuickDaily clicked');
        setError('');
        setSuccess('');
        setGenerating(true);
        try {
            console.log('[AI] Calling aiApi.quickDaily()...');
            const res = await aiApi.quickDaily();
            console.log('[AI] Response received:', res.data);
            setSelectedChat(null);
            setMessages([]);
            setSummary({ context_type: 'daily' });
            setQuickResult({
                title: 'Денний брифінг',
                content: res.data.content,
                reportType: 'daily',
            });
            setSuccess('Денний брифінг згенеровано і збережено.');
        } catch (err: any) {
            console.error('[AI] Error:', err);
            const detail = err.response?.data?.detail || err.message || 'Не вдалося згенерувати денний брифінг';
            setError(detail);
        } finally {
            setGenerating(false);
        }
    };

    const handleQuickSubmit = async (e: FormEvent) => {
        e.preventDefault();
        try {
            if (showQuickModal === 'case') {
                await aiApi.quickCase({ case_id: quickInput });
            } else if (showQuickModal === 'person') {
                await aiApi.quickPerson({ person_id: quickInput });
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Контекст поки недоступний');
        } finally {
            setShowQuickModal(null);
            setQuickInput('');
        }
    };

    const handleSaveCurrentReport = async () => {
        const content = draftAssistant || quickResult?.content || messages.filter(m => m.role === 'assistant').slice(-1)[0]?.content;
        if (!content) return;
        try {
            await aiApi.saveReport({
                title: selectedChat?.title || quickResult?.title || 'Звіт ШІ',
                report_type: selectedChat?.context_type || quickResult?.reportType || 'custom',
                context_id: selectedChat?.context_id || quickResult?.contextId,
                content,
            });
            setSuccess('Звіт збережено.');
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося зберегти звіт');
        }
    };

    const handleDeleteChat = async (chatId: string) => {
        if (!confirm('Видалити цей чат?')) return;
        try {
            await aiApi.deleteChat(chatId);
            if (selectedChat?.id === chatId) {
                setSelectedChat(null);
                setMessages([]);
                setSummary(null);
            }
            const chatsRes = await aiApi.chats();
            setChats(chatsRes.data);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося видалити чат');
        }
    };

    const renderSummary = () => {
        if (selectedChat && summary?.context_type === 'group') {
            return (
                <>
                    <div><strong>Група:</strong> {summary.group_name}</div>
                    <div><strong>TG ID:</strong> {summary.telegram_id}</div>
                    <div><strong>Повідомлень:</strong> {summary.messages_count}</div>
                    <div style={{ marginTop: '12px' }}><strong>Останні події:</strong></div>
                    {(summary.recent_events || []).map((event: any, index: number) => (
                        <div key={index} style={{ fontSize: '13px', color: 'var(--fw-text-muted)', marginTop: '8px' }}>
                            {event.timestamp || '—'}<br />
                            {event.text || '—'}
                        </div>
                    ))}
                </>
            );
        }
        if (quickResult?.reportType === 'daily' || summary?.context_type === 'daily') {
            const stats = summary?.stats || {};
            return (
                <>
                    <div><strong>Повідомлення за добу:</strong> {stats.messages ?? '—'}</div>
                    <div><strong>Фото:</strong> {stats.photos ?? '—'}</div>
                    <div><strong>Обличчя:</strong> {stats.faces ?? '—'}</div>
                </>
            );
        }
        return <div style={{ color: 'var(--fw-text-muted)' }}>Загальний контекст без додаткового зведення.</div>;
    };

    const lastAssistantContent = draftAssistant || messages.filter(m => m.role === 'assistant').slice(-1)[0]?.content || quickResult?.content || '';

    return (
        <div className="animate-fade-in" style={{ display: 'grid', gridTemplateColumns: '280px minmax(0, 1fr) 260px', gap: '20px', minHeight: 'calc(100vh - 120px)' }}>
            <div className="glass-card" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '16px', minHeight: 0 }}>
                <div>
                    <div style={{ fontSize: '18px', fontWeight: 800, marginBottom: '12px' }}>Швидкі дії</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <button className="btn-primary" onClick={handleQuickDaily} disabled={generating}>
                            {generating ? '⏳ Генерація...' : '📊 Денний брифінг'}
                        </button>
                        <button className="btn-secondary" onClick={() => setShowQuickModal('case')}>📁 Аналіз справи</button>
                        <button className="btn-secondary" onClick={() => setShowQuickModal('person')}>👤 Аналіз особи</button>
                    </div>
                </div>

                <div style={{ padding: '12px', borderRadius: '10px', background: 'rgba(255,255,255,0.04)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: status.available ? '#22c55e' : '#ef4444', display: 'inline-block' }} />
                        <span>{status.available ? `${status.model} · активний` : 'Ollama недоступний'}</span>
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--fw-text-muted)', marginTop: '6px' }}>Версія: {status.version || 'unknown'}</div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontSize: '16px', fontWeight: 700 }}>Чати</div>
                    <button className="btn-secondary" onClick={() => setShowNewChat(true)}>+ Новий чат</button>
                </div>

                <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px', minHeight: 0 }}>
                    {chats.map(chat => (
                        <div
                            key={chat.id}
                            onClick={() => loadChat(chat)}
                            style={{
                                padding: '12px',
                                borderRadius: '10px',
                                cursor: 'pointer',
                                background: selectedChat?.id === chat.id ? 'rgba(56,189,248,0.15)' : 'rgba(255,255,255,0.03)',
                                border: selectedChat?.id === chat.id ? '1px solid rgba(56,189,248,0.4)' : '1px solid rgba(255,255,255,0.05)',
                            }}
                        >
                            <div style={{ fontWeight: 700, marginBottom: '6px' }}>{chat.title}</div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
                                <span className="badge badge-primary">{chat.context_type}</span>
                                <button className="btn-danger" style={{ padding: '6px 10px' }} onClick={(e) => { e.stopPropagation(); handleDeleteChat(chat.id); }}>×</button>
                            </div>
                            <div style={{ marginTop: '6px', fontSize: '12px', color: 'var(--fw-text-dim)' }}>
                                {chat.updated_at ? new Date(chat.updated_at).toLocaleString('uk-UA') : '—'}
                            </div>
                        </div>
                    ))}
                    {!loading && chats.length === 0 && (
                        <div style={{ color: 'var(--fw-text-dim)', textAlign: 'center', padding: '20px 0' }}>Чатів поки немає</div>
                    )}
                </div>
            </div>

            <div className="glass-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
                {error && <div style={{ marginBottom: '12px', color: '#ef4444' }}>{error}</div>}
                {success && <div style={{ marginBottom: '12px', color: '#22c55e' }}>{success}</div>}

                {!selectedChat && !quickResult && (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, textAlign: 'center', gap: '16px' }}>
                        <div style={{ fontSize: '48px' }}>🤖</div>
                        <h1 style={{ margin: 0 }}>Оберіть чат або створіть новий</h1>
                        <div style={{ color: 'var(--fw-text-muted)' }}>Швидкий доступ до локального ШІ FaceWatch через Ollama.</div>
                        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'center' }}>
                            <button className="btn-primary" onClick={handleQuickDaily} disabled={generating}>
                                {generating ? '⏳ Генерація...' : '📊 Денний брифінг'}
                            </button>
                            <button className="btn-secondary" onClick={() => setShowNewChat(true)}>+ Новий чат</button>
                        </div>
                    </div>
                )}

                {(selectedChat || quickResult) && (
                    <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
                            <div>
                                <div style={{ fontSize: '22px', fontWeight: 800 }}>{selectedChat?.title || quickResult?.title}</div>
                                <span className="badge badge-primary">{selectedChat?.context_type || quickResult?.reportType || 'general'}</span>
                            </div>
                            <button className="btn-secondary" onClick={handleSaveCurrentReport} disabled={!lastAssistantContent}>
                                Зберегти звіт
                            </button>
                        </div>

                        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px', paddingRight: '6px' }}>
                            {quickResult && (
                                <div style={{ alignSelf: 'stretch', background: 'rgba(59,130,246,0.12)', padding: '14px', borderRadius: '12px' }}>
                                    <ReactMarkdown>{quickResult.content}</ReactMarkdown>
                                </div>
                            )}
                            {messages.map(message => (
                                <div
                                    key={message.id}
                                    style={{
                                        alignSelf: message.role === 'user' ? 'flex-end' : 'flex-start',
                                        maxWidth: '85%',
                                        background: message.role === 'user' ? 'rgba(17,24,39,0.85)' : 'rgba(59,130,246,0.12)',
                                        padding: '14px',
                                        borderRadius: '12px',
                                    }}
                                >
                                    {message.role === 'assistant' ? <ReactMarkdown>{message.content}</ReactMarkdown> : <div style={{ whiteSpace: 'pre-wrap' }}>{message.content}</div>}
                                </div>
                            ))}
                            {draftAssistant && (
                                <div style={{ alignSelf: 'flex-start', maxWidth: '85%', background: 'rgba(59,130,246,0.12)', padding: '14px', borderRadius: '12px' }}>
                                    <ReactMarkdown>{draftAssistant}</ReactMarkdown>
                                </div>
                            )}
                            {sending && !draftAssistant && (
                                <div style={{ color: 'var(--fw-text-muted)' }}>●●●</div>
                            )}
                            <div ref={messagesEndRef} />
                        </div>

                        {selectedChat && (
                            <div style={{ marginTop: '16px', display: 'flex', gap: '10px', alignItems: 'flex-end' }}>
                                <textarea
                                    className="input-field"
                                    style={{ minHeight: '88px', resize: 'vertical' }}
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' && !e.shiftKey) {
                                            e.preventDefault();
                                            handleSend();
                                        }
                                    }}
                                    placeholder="Напишіть запит до локального ШІ..."
                                    disabled={sending}
                                />
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                    <button className="btn-primary" onClick={handleSend} disabled={sending || !input.trim()}>Надіслати</button>
                                    <button className="btn-danger" onClick={() => abortRef.current?.abort()} disabled={!sending}>Скасувати</button>
                                </div>
                            </div>
                        )}
                    </>
                )}
            </div>

            <div className="glass-card" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ fontSize: '16px', fontWeight: 800 }}>Контекст</div>
                {renderSummary()}
            </div>

            {showNewChat && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div className="glass-card" style={{ width: 'min(560px, 92vw)', padding: '24px' }}>
                        <h2 style={{ marginTop: 0 }}>Новий чат</h2>
                        <form onSubmit={handleCreateChat}>
                            <div style={{ display: 'grid', gap: '12px' }}>
                                <select className="input-field" value={newChatForm.context_type} onChange={(e) => setNewChatForm(prev => ({ ...prev, context_type: e.target.value as ContextType, context_id: '' }))}>
                                    <option value="general">Загальний</option>
                                    <option value="group">Група</option>
                                    <option value="daily">Денний</option>
                                    <option value="case">Провадження</option>
                                    <option value="person">Особа</option>
                                </select>
                                {newChatForm.context_type === 'group' && (
                                    <select className="input-field" value={newChatForm.context_id} onChange={(e) => setNewChatForm(prev => ({ ...prev, context_id: e.target.value }))} required>
                                        <option value="">Оберіть групу</option>
                                        {groups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}
                                    </select>
                                )}
                                {newChatForm.context_type === 'case' && (
                                    <input className="input-field" placeholder="case_id" value={newChatForm.context_id} onChange={(e) => setNewChatForm(prev => ({ ...prev, context_id: e.target.value }))} required />
                                )}
                                {newChatForm.context_type === 'person' && (
                                    <input className="input-field" placeholder="person_id" value={newChatForm.context_id} onChange={(e) => setNewChatForm(prev => ({ ...prev, context_id: e.target.value }))} required />
                                )}
                                <textarea className="input-field" style={{ minHeight: '120px' }} placeholder="Перше питання" value={newChatForm.first_message} onChange={(e) => setNewChatForm(prev => ({ ...prev, first_message: e.target.value }))} required />
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                                <button type="button" className="btn-secondary" onClick={() => setShowNewChat(false)}>Скасувати</button>
                                <button type="submit" className="btn-primary">Почати</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {showQuickModal && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div className="glass-card" style={{ width: 'min(420px, 92vw)', padding: '24px' }}>
                        <h2 style={{ marginTop: 0 }}>{showQuickModal === 'case' ? 'Аналіз справи' : 'Аналіз особи'}</h2>
                        <form onSubmit={handleQuickSubmit}>
                            <input className="input-field" placeholder={showQuickModal === 'case' ? 'case_id' : 'person_id'} value={quickInput} onChange={(e) => setQuickInput(e.target.value)} required />
                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                                <button type="button" className="btn-secondary" onClick={() => setShowQuickModal(null)}>Скасувати</button>
                                <button type="submit" className="btn-primary">Запустити</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
