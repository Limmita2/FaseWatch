import { useEffect, useState } from 'react';

import { platformSourcesApi } from '@/services/api';

export default function WaAccountsPage() {
    const [groups, setGroups] = useState<any[]>([]);
    const [status, setStatus] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    const load = () => {
        Promise.all([
            platformSourcesApi.status('whatsapp'),
            platformSourcesApi.groups('whatsapp'),
        ]).then(([statusResponse, groupsResponse]) => {
            setStatus(statusResponse.data);
            setGroups(groupsResponse.data || []);
        }).finally(() => setLoading(false));
    };

    useEffect(() => {
        load();
        const timer = window.setInterval(load, 15000);
        return () => window.clearInterval(timer);
    }, []);

    const handleToggle = async (groupId: string) => {
        await platformSourcesApi.toggleGroup('whatsapp', groupId);
        load();
    };

    if (loading) {
        return (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '80px' }}>
                <div className="spinner" />
            </div>
        );
    }

    return (
        <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                <h1 style={{ fontSize: '24px', fontWeight: 800, color: 'var(--fw-primary)', textTransform: 'uppercase', letterSpacing: '2px', textShadow: 'var(--fw-glow-primary)' }}>
                    [ WHATSAPP АКАУНТ ]
                </h1>
                <span className="badge badge-primary">ГРУП: {groups.length}</span>
            </div>

            <div className="glass-card" style={{ display: 'grid', gap: '16px' }}>
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                    <span className={`badge ${status?.status === 'active' ? 'badge-success' : 'badge-warning'}`}>
                        СТАТУС: {(status?.status || 'inactive').toUpperCase()}
                    </span>
                    <span className="badge badge-primary">
                        LIVE: {status?.groups_live ?? 0}
                    </span>
                    <span className="badge badge-primary">
                        HISTORY: {status?.groups_history_loaded ?? 0}
                    </span>
                </div>
                <div>
                    <div style={{ fontWeight: 700, marginBottom: '8px' }}>Підключення</div>
                    <div style={{ color: 'var(--fw-text-muted)', lineHeight: 1.6 }}>
                        Сервіс працює через Baileys у контейнері <code>facewatch_whatsapp</code>.
                        Перша авторизація виконується по QR-коду з логів контейнера.
                    </div>
                </div>
                <div>
                    <div style={{ fontWeight: 700, marginBottom: '8px' }}>Команди</div>
                    <div style={{ color: 'var(--fw-text-muted)', lineHeight: 1.6 }}>
                        <code>docker compose build facewatch_whatsapp</code><br />
                        <code>docker compose up -d facewatch_whatsapp</code><br />
                        <code>docker logs -f facewatch_whatsapp</code>
                    </div>
                </div>
                <div>
                    <div style={{ fontWeight: 700, marginBottom: '8px' }}>Сесія</div>
                    <div style={{ color: 'var(--fw-text-muted)', lineHeight: 1.6 }}>
                        Дані авторизації зберігаються в <code>./whatsapp-session</code>. При logout контейнер завершується і після рестарту покаже новий QR.
                    </div>
                </div>
            </div>

            <div className="glass-card table-container">
                <table>
                    <thead>
                        <tr>
                            <th>ГРУПА</th>
                            <th>REMOTE JID</th>
                            <th>ІСТОРІЯ</th>
                            <th>МОНІТОРИНГ</th>
                        </tr>
                    </thead>
                    <tbody>
                        {groups.map((group: any) => (
                            <tr key={group.id}>
                                <td style={{ fontWeight: 500 }}>{group.name}</td>
                                <td style={{ fontSize: '13px', color: 'var(--fw-text-muted)' }}>{group.external_id || '—'}</td>
                                <td>
                                    <span className={`badge ${group.history_loaded ? 'badge-success' : 'badge-warning'}`}>
                                        {group.history_loaded ? `ГОТОВО (${group.history_load_progress})` : `SYNC ${group.history_load_progress}`}
                                    </span>
                                </td>
                                <td>
                                    <button className={group.is_active ? 'btn-secondary' : 'btn-primary'} onClick={() => handleToggle(group.group_id)}>
                                        {group.is_active ? 'ПАУЗА' : 'ВКЛЮЧИТИ'}
                                    </button>
                                </td>
                            </tr>
                        ))}
                        {groups.length === 0 && (
                            <tr>
                                <td colSpan={4} style={{ textAlign: 'center', color: 'var(--fw-text-dim)', padding: '24px' }}>
                                    Поки немає підключених WhatsApp-груп
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
