import { useEffect, useState } from 'react';
import { dashboardApi } from '@/services/api';

interface DashboardData {
    groups: number;
    messages: number;
    faces: number;
    persons: number;
    pending_identifications: number;
    recent_messages: Array<{
        id: string;
        group_name: string;
        text: string | null;
        has_photo: boolean;
        timestamp: string | null;
    }>;
}

export default function DashboardPage() {
    const [data, setData] = useState<DashboardData | null>(null);

    useEffect(() => {
        dashboardApi.get().then((r) => setData(r.data)).catch(console.error);
    }, []);

    if (!data) return <div style={{ display: 'flex', justifyContent: 'center', padding: '80px' }}><div className="spinner" /></div>;

    const stats = [
        { label: 'Групи', value: data.groups, icon: '👥' },
        { label: 'Повідомлень', value: data.messages, icon: '💬' },
        { label: 'Облич', value: data.faces, icon: '🧑' },
        { label: 'Персон', value: data.persons, icon: '👤' },
        { label: 'Очікує перевірки', value: data.pending_identifications, icon: '⏳' },
    ];

    return (
        <div className="animate-fade-in">
            <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '24px' }}>📊 Дашборд</h1>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '32px' }}>
                {stats.map((s) => (
                    <div key={s.label} className="glass-card stat-card">
                        <span style={{ fontSize: '20px' }}>{s.icon}</span>
                        <span className="stat-value">{s.value.toLocaleString()}</span>
                        <span className="stat-label">{s.label}</span>
                    </div>
                ))}
            </div>

            <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>🕐 Останні надходження</h2>
            <div className="glass-card table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Група</th>
                            <th>Текст</th>
                            <th>Фото</th>
                            <th>Час</th>
                        </tr>
                    </thead>
                    <tbody>
                        {data.recent_messages.map((msg) => (
                            <tr key={msg.id}>
                                <td><span className="badge badge-primary">{msg.group_name || '—'}</span></td>
                                <td style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {msg.text || <span style={{ color: 'var(--fw-text-dim)' }}>—</span>}
                                </td>
                                <td>{msg.has_photo ? '📷' : '—'}</td>
                                <td style={{ fontSize: '13px', color: 'var(--fw-text-muted)' }}>
                                    {msg.timestamp ? new Date(msg.timestamp).toLocaleString('uk-UA') : '—'}
                                </td>
                            </tr>
                        ))}
                        {data.recent_messages.length === 0 && (
                            <tr><td colSpan={4} style={{ textAlign: 'center', color: 'var(--fw-text-dim)', padding: '24px' }}>Повідомлень поки немає</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
