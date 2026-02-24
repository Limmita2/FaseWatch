import { useEffect, useState } from 'react';
import { messagesApi, groupsApi } from '@/services/api';

export default function MessagesPage() {
    const [messages, setMessages] = useState<any[]>([]);
    const [groups, setGroups] = useState<any[]>([]);
    const [groupFilter, setGroupFilter] = useState('');
    const [photoOnly, setPhotoOnly] = useState(false);
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);

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

    return (
        <div className="animate-fade-in">
            <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '24px' }}>💬 Стрічка повідомлень</h1>

            <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap' }}>
                <select className="input-field" style={{ width: '200px' }} value={groupFilter} onChange={e => { setGroupFilter(e.target.value); setPage(1); }}>
                    <option value="">Усі групи</option>
                    {groups.map((g: any) => <option key={g.id} value={g.id}>{g.name}</option>)}
                </select>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '14px', color: 'var(--fw-text-muted)', cursor: 'pointer' }}>
                    <input type="checkbox" checked={photoOnly} onChange={() => { setPhotoOnly(!photoOnly); setPage(1); }} />
                    Тільки з фото
                </label>
            </div>

            {loading ? (
                <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}><div className="spinner" /></div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {messages.map((msg: any) => (
                        <div key={msg.id} className="glass-card" style={{ padding: '16px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                                <span className="badge badge-primary">{msg.group_name || '—'}</span>
                                {msg.sender_name && <span style={{ fontSize: '13px', fontWeight: 600 }}>{msg.sender_name}</span>}
                                <span style={{ fontSize: '12px', color: 'var(--fw-text-dim)', marginLeft: 'auto' }}>
                                    {msg.timestamp ? new Date(msg.timestamp).toLocaleString('uk-UA') : '—'}
                                </span>
                                {msg.has_photo && <span>📷</span>}
                            </div>
                            {msg.text && <p style={{ fontSize: '14px', lineHeight: '1.5', color: 'var(--fw-text)' }}>{msg.text}</p>}
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
                <button className="btn-secondary" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Назад</button>
                <span style={{ padding: '10px', color: 'var(--fw-text-muted)', fontSize: '14px' }}>Сторінка {page}</span>
                <button className="btn-secondary" disabled={messages.length < 50} onClick={() => setPage(p => p + 1)}>Далі →</button>
            </div>
        </div>
    );
}
