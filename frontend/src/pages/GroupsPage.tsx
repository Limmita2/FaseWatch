import { useEffect, useState } from 'react';
import { groupsApi } from '@/services/api';

export default function GroupsPage() {
    const [groups, setGroups] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        groupsApi.list().then(r => { setGroups(r.data); setLoading(false); }).catch(() => setLoading(false));
    }, []);

    if (loading) return <div style={{ display: 'flex', justifyContent: 'center', padding: '80px' }}><div className="spinner" /></div>;

    return (
        <div className="animate-fade-in">
            <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '24px' }}>👥 Telegram-групи</h1>
            <div className="glass-card table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Назва</th>
                            <th>Telegram ID</th>
                            <th>Статус бота</th>
                            <th>Останнє повідомлення</th>
                        </tr>
                    </thead>
                    <tbody>
                        {groups.map((g: any) => (
                            <tr key={g.id}>
                                <td style={{ fontWeight: 500 }}>{g.name}</td>
                                <td style={{ fontSize: '13px', color: 'var(--fw-text-muted)' }}>{g.telegram_id || '—'}</td>
                                <td>
                                    <span className={`badge ${g.bot_active ? 'badge-success' : 'badge-danger'}`}>
                                        {g.bot_active ? '🟢 Активний' : '🔴 Неактивний'}
                                    </span>
                                </td>
                                <td style={{ fontSize: '13px', color: 'var(--fw-text-muted)' }}>
                                    {g.last_message_at ? new Date(g.last_message_at).toLocaleString('uk-UA') : '—'}
                                </td>
                            </tr>
                        ))}
                        {groups.length === 0 && <tr><td colSpan={4} style={{ textAlign: 'center', color: 'var(--fw-text-dim)', padding: '24px' }}>Груп поки немає</td></tr>}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
