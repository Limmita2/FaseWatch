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
            <h1 style={{ fontSize: '24px', fontWeight: 800, marginBottom: '24px', color: 'var(--fw-primary)', textTransform: 'uppercase', letterSpacing: '2px', textShadow: 'var(--fw-glow-primary)' }}>
                [ ДЖЕРЕЛА TELEGRAM ]
            </h1>
            <div className="glass-card table-container">
                <table>
                    <thead>
                        <tr>
                            <th>НАЗВА КАНАЛУ</th>
                            <th>TG_ID</th>
                            <th>СТАТУС БОТА</th>
                            <th>ОСТАННІЙ ПІНГ</th>
                        </tr>
                    </thead>
                    <tbody>
                        {groups.map((g: any) => (
                            <tr key={g.id}>
                                <td style={{ fontWeight: 500 }}>{g.name}</td>
                                <td style={{ fontSize: '13px', color: 'var(--fw-text-muted)' }}>{g.telegram_id || '—'}</td>
                                <td>
                                    <span className={`badge ${g.bot_active ? 'badge-success' : 'badge-danger'}`}>
                                        {g.bot_active ? '[ АКТИВНО ]' : '[ ОФЛАЙН ]'}
                                    </span>
                                </td>
                                <td style={{ fontSize: '13px', color: 'var(--fw-text-muted)' }}>
                                    {g.last_message_at ? new Date(g.last_message_at).toLocaleString('uk-UA') : '—'}
                                </td>
                            </tr>
                        ))}
                        {groups.length === 0 && <tr><td colSpan={4} style={{ textAlign: 'center', color: 'var(--fw-text-dim)', padding: '24px' }}>Джерел поки немає</td></tr>}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
