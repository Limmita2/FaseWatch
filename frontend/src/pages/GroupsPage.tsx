import { useEffect, useState } from 'react';
import { groupsApi } from '@/services/api';
import { useAuthStore } from '@/store/authStore';

export default function GroupsPage() {
    const [groups, setGroups] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const role = useAuthStore(state => state.role);

    const loadGroups = () => {
        groupsApi.list().then(r => { setGroups(r.data); setLoading(false); }).catch(() => setLoading(false));
    };

    useEffect(() => {
        loadGroups();
    }, []);

    const handleToggle = async (id: string, current: boolean) => {
        try {
            await groupsApi.toggleVisibility(id);
            setGroups(groups.map(g => g.id === id ? { ...g, is_public: !current } : g));
        } catch (e: any) {
            if (e.response?.status === 403) {
                alert("Тільки головний адміністратор (admin) може змінювати видимість груп.");
            } else {
                alert("Помилка при зміні видимості.");
            }
        }
    };

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
                            {role === 'admin' && <th>В ПОШУКУ</th>}
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
                                {role === 'admin' && (
                                    <td>
                                        <input 
                                            type="checkbox" 
                                            checked={g.is_public} 
                                            onChange={() => handleToggle(g.id, g.is_public)}
                                            style={{ cursor: 'pointer', transform: 'scale(1.3)', accentColor: 'var(--fw-primary)' }}
                                            title="Вимкніть, щоб звичайні юзери не бачили цю групу в пошуку"
                                        />
                                    </td>
                                )}
                            </tr>
                        ))}
                        {groups.length === 0 && <tr><td colSpan={role === 'admin' ? 5 : 4} style={{ textAlign: 'center', color: 'var(--fw-text-dim)', padding: '24px' }}>Джерел поки немає</td></tr>}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
