import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { messagesApi, groupsApi } from '@/services/api';

export default function MessagesPage() {
    const [messages, setMessages] = useState<any[]>([]);
    const [groups, setGroups] = useState<any[]>([]);
    const [groupFilter, setGroupFilter] = useState('');
    const [photoOnly, setPhotoOnly] = useState(false);
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [photoIdQuery, setPhotoIdQuery] = useState('');
    const [highlightMessageId, setHighlightMessageId] = useState<string | null>(null);
    const navigate = useNavigate();

    // Підсвічування телефонних номерів у тексті
    const highlightPhones = (text: string | null | undefined) => {
        if (!text) return null;
        const phoneRegex = /(?<!\d)((?:\+?38)?(?:[\s\-(]*?)0(?:[\s\-)]*?)(?:39|50|63|66|67|68|73|91|92|93|94|95|96|97|98|99)(?:[\s\-)]*?\d){7})(?!\d)/g;
        const parts = text.split(phoneRegex);
        return parts.map((part, i) => {
            if (phoneRegex.test(part)) {
                phoneRegex.lastIndex = 0;
                return <span key={i} style={{ color: '#22c55e', fontWeight: 700, textDecoration: 'underline', cursor: 'pointer' }} onClick={(e) => { e.stopPropagation(); navigate(`/search?tab=phone&q=${encodeURIComponent(part.replace(/[^\d+]/g, ''))}`); }} title="Шукати цей номер">{part}</span>;
            }
            return part;
        });
    };

    useEffect(() => {
        groupsApi.list().then(r => setGroups(r.data)).catch(() => { });
    }, []);

    useEffect(() => {
        setLoading(true);
        const params: Record<string, any> = { page };
        if (groupFilter) params.group_id = groupFilter;
        if (photoOnly) params.only_with_photo = true;
        messagesApi.list(params).then(r => { setMessages(r.data); setLoading(false); }).catch(() => setLoading(false));
    }, [page, groupFilter, photoOnly]);

    const handleSearchPhotoId = async () => {
        if (!photoIdQuery.trim()) return;
        setLoading(true);
        try {
            const { data } = await messagesApi.findPage({
                photo_id: photoIdQuery.trim(),
                group_id: groupFilter || undefined,
                only_with_photo: photoOnly || undefined
            });
            if (data.page) {
                setPage(data.page);
                setHighlightMessageId(data.message_id);
            }
        } catch (e: any) {
            alert(e?.response?.data?.detail || 'Фото з таким ID не знайдено');
        }
        setLoading(false);
    };

    useEffect(() => {
        if (highlightMessageId && !loading && messages.length > 0) {
            const el = document.getElementById(`msg-${highlightMessageId}`);
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                // Optional: remove highlight after some time
                setTimeout(() => setHighlightMessageId(null), 5000);
            }
        }
    }, [messages, highlightMessageId, loading]);

    return (
        <div className="animate-fade-in">
            <h1 style={{ fontSize: '24px', fontWeight: 800, marginBottom: '24px', color: 'var(--fw-primary)', textTransform: 'uppercase', letterSpacing: '2px', textShadow: 'var(--fw-glow-primary)' }}>
                [ СТРІЧКА ПОВІДОМЛЕНЬ ]
            </h1>

            <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap' }}>
                <select className="input-field" style={{ width: '200px' }} value={groupFilter} onChange={e => { setGroupFilter(e.target.value); setPage(1); }}>
                    <option value="">Усі групи</option>
                    {groups.map((g: any) => <option key={g.id} value={g.id}>{g.name}</option>)}
                </select>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '14px', color: 'var(--fw-text-muted)', cursor: 'pointer', marginRight: 'auto' }}>
                    <input type="checkbox" checked={photoOnly} onChange={() => { setPhotoOnly(!photoOnly); setPage(1); }} />
                    Тільки з фото
                </label>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <input className="input-field" style={{ width: '250px' }} placeholder="Пошук за ID фото..." value={photoIdQuery} onChange={e => setPhotoIdQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearchPhotoId()} />
                    <button className="btn-secondary" onClick={handleSearchPhotoId}>Знайти сторінку</button>
                </div>
            </div>

            {loading ? (
                <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}><div className="spinner" /></div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {messages.map((msg: any) => (
                        <div
                            key={msg.id}
                            id={`msg-${msg.id}`}
                            className="glass-card"
                            style={{
                                padding: '16px',
                                border: highlightMessageId === msg.id ? '2px solid var(--fw-success)' : '1px solid transparent',
                                boxShadow: highlightMessageId === msg.id ? '0 0 15px rgba(34, 197, 94, 0.3)' : 'none',
                                transition: 'all 0.5s ease'
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                                <span className="badge badge-primary">{msg.group_name || '—'}</span>
                                {msg.sender_name && <span style={{ fontSize: '13px', fontWeight: 600 }}>{msg.sender_name}</span>}
                                <span style={{ fontSize: '12px', color: 'var(--fw-text-dim)', marginLeft: 'auto' }}>
                                    {msg.timestamp ? new Date(msg.timestamp).toLocaleString('uk-UA') : '—'}
                                </span>
                                {msg.has_photo && <span>📷</span>}
                            </div>
                            {msg.text && <p style={{ fontSize: '14px', lineHeight: '1.5', color: 'var(--fw-text)', fontFamily: `'Courier New', Courier, monospace` }}>{highlightPhones(msg.text)}</p>}
                            {msg.photo_path && (
                                <img
                                    src={`/files/${msg.photo_path.replace(/^\/mnt\/qnap_photos\//, '')}`}
                                    alt="photo"
                                    style={{ maxWidth: 300, borderRadius: 'var(--fw-radius-sm)', marginTop: '8px' }}
                                    onError={(e) => (e.currentTarget.style.display = 'none')}
                                />
                            )}
                        </div>
                    ))}
                    {messages.length === 0 && <p style={{ textAlign: 'center', color: 'var(--fw-text-dim)', padding: '40px' }}>Повідомлень не знайдено</p>}
                </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '20px' }}>
                <button className="btn-secondary" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← ПОПЕРЕДНЯ СТОРІНКА</button>
                <span style={{ padding: '10px', color: 'var(--fw-primary)', fontSize: '14px', fontWeight: 700 }}>СТОРІНКА {page}</span>
                <button className="btn-secondary" disabled={messages.length < 50} onClick={() => setPage(p => p + 1)}>НАСТУПНА СТОРІНКА →</button>
            </div>
        </div>
    );
}
