import { useState, useEffect } from 'react';
import { usersApi } from '@/services/api';

interface User {
    id: string;
    username: string;
    role: string;
    description?: string;
    last_ip?: string;
    allowed_ip: string;
}

export default function UsersPage() {
    const [users, setUsers] = useState<User[]>([]);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({ username: '', password: '', role: 'operator', description: '' });
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    const fetchUsers = async () => {
        try {
            const res = await usersApi.list();
            setUsers(res.data);
        } catch {
            setError('Помилка завантаження користувачів');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchUsers(); }, []);

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setSuccess('');
        try {
            await usersApi.create(form);
            setForm({ username: '', password: '', role: 'operator', description: '' });
            setShowForm(false);
            setSuccess('Користувача створено');
            fetchUsers();
            setTimeout(() => setSuccess(''), 3000);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Помилка створення користувача');
        }
    };

    const handleDelete = async (id: string, username: string) => {
        if (!confirm(`Видалити користувача "${username}"?`)) return;
        try {
            await usersApi.delete(id);
            setSuccess(`Користувача "${username}" видалено`);
            fetchUsers();
            setTimeout(() => setSuccess(''), 3000);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Помилка видалення');
        }
    };

    const handleUpdateIp = async (id: string, newIp: string) => {
        try {
            await usersApi.updateIp(id, newIp);
            setSuccess('Налаштування IP оновлено');
            setTimeout(() => setSuccess(''), 2000);
            setUsers(users.map(u => u.id === id ? { ...u, allowed_ip: newIp } : u));
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Помилка оновлення IP');
            setTimeout(() => setError(''), 3000);
        }
    };

    if (loading) return (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
            <div className="spinner" />
        </div>
    );

    return (
        <div className="animate-fade-in" style={{ maxWidth: '100%', padding: '0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                <h1 style={{ fontSize: '24px', fontWeight: 800, color: 'var(--fw-primary)', textTransform: 'uppercase', letterSpacing: '2px', textShadow: 'var(--fw-glow-primary)' }}>
                    [ ОПЕРАТОРИ СИСТЕМИ ]
                </h1>
                <button
                    className={showForm ? 'btn-secondary' : 'btn-primary'}
                    onClick={() => { setShowForm(!showForm); setError(''); }}
                    style={{ padding: '10px 24px', fontSize: '15px' }}
                >
                    {showForm ? '✕ Скасувати' : '+ Додати користувача'}
                </button>
            </div>

            {error && (
                <div style={{ padding: '12px 16px', borderRadius: '8px', background: 'rgba(239,68,68,0.15)', color: '#ef4444', marginBottom: '16px', fontSize: '14px' }}>
                    ⚠️ {error}
                </div>
            )}
            {success && (
                <div style={{ padding: '12px 16px', borderRadius: '8px', background: 'rgba(34,197,94,0.15)', color: '#22c55e', marginBottom: '16px', fontSize: '14px' }}>
                    ✅ {success}
                </div>
            )}

            {showForm && (
                <div className="glass-card" style={{ padding: '28px', marginBottom: '24px' }}>
                    <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '20px' }}>Новий користувач</h2>
                    <form onSubmit={handleCreate}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                            <div>
                                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--fw-text-muted)' }}>Логін *</label>
                                <input
                                    className="input-field"
                                    type="text"
                                    value={form.username}
                                    required
                                    placeholder="Введіть логін"
                                    onChange={e => setForm({ ...form, username: e.target.value })}
                                    style={{ width: '100%', padding: '10px 14px', fontSize: '15px' }}
                                />
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--fw-text-muted)' }}>Пароль *</label>
                                <input
                                    className="input-field"
                                    type="password"
                                    value={form.password}
                                    required
                                    placeholder="Введіть пароль"
                                    onChange={e => setForm({ ...form, password: e.target.value })}
                                    style={{ width: '100%', padding: '10px 14px', fontSize: '15px' }}
                                />
                            </div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '16px', marginBottom: '20px' }}>
                            <div>
                                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--fw-text-muted)' }}>Роль</label>
                                <select
                                    className="input-field"
                                    value={form.role}
                                    onChange={e => setForm({ ...form, role: e.target.value })}
                                    style={{ width: '100%', padding: '10px 14px', fontSize: '15px' }}
                                >
                                    <option value="operator">Оператор</option>
                                    <option value="admin">Адміністратор</option>
                                </select>
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--fw-text-muted)' }}>Опис</label>
                                <input
                                    className="input-field"
                                    type="text"
                                    value={form.description}
                                    placeholder="Наприклад: Оператор чергової зміни"
                                    onChange={e => setForm({ ...form, description: e.target.value })}
                                    style={{ width: '100%', padding: '10px 14px', fontSize: '15px' }}
                                />
                            </div>
                        </div>
                        <button type="submit" className="btn-primary" style={{ padding: '12px 32px', fontSize: '15px' }}>
                            ✅ Створити користувача
                        </button>
                    </form>
                </div>
            )}

            <div className="glass-card" style={{ padding: '0', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ background: 'rgba(255,255,255,0.05)', borderBottom: '1px solid var(--fw-primary)' }}>
                            <th style={{ padding: '14px 20px', textAlign: 'left', fontSize: '11px', fontWeight: 700, color: 'var(--fw-primary)', textTransform: 'uppercase', letterSpacing: '2px' }}>ІМ'Я КОРИСТУВАЧА</th>
                            <th style={{ padding: '14px 20px', textAlign: 'left', fontSize: '11px', fontWeight: 700, color: 'var(--fw-primary)', textTransform: 'uppercase', letterSpacing: '2px' }}>РІВЕНЬ ДОСТУПУ</th>
                            <th style={{ padding: '14px 20px', textAlign: 'left', fontSize: '11px', fontWeight: 700, color: 'var(--fw-primary)', textTransform: 'uppercase', letterSpacing: '2px' }}>ОПИС</th>
                            <th style={{ padding: '14px 20px', textAlign: 'center', fontSize: '11px', fontWeight: 700, color: 'var(--fw-primary)', textTransform: 'uppercase', letterSpacing: '2px' }}>IP ДОСТУП</th>
                            <th style={{ padding: '14px 20px', textAlign: 'right', fontSize: '11px', fontWeight: 700, color: 'var(--fw-primary)', textTransform: 'uppercase', letterSpacing: '2px', width: '100px' }}>ДІЇ</th>
                        </tr>
                    </thead>
                    <tbody>
                        {users.map(u => (
                            <tr key={u.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                <td style={{ padding: '14px 20px', fontSize: '15px', fontWeight: 500 }}>
                                    👤 {u.username}
                                </td>
                                <td style={{ padding: '14px 20px' }}>
                                    <span style={{
                                        padding: '4px 12px',
                                        borderRadius: 'var(--fw-radius-sm)',
                                        fontSize: '11px',
                                        fontWeight: 700,
                                        letterSpacing: '1px',
                                        background: u.role === 'admin' ? 'rgba(0,210,255,0.1)' : 'rgba(0,255,136,0.1)',
                                        color: u.role === 'admin' ? 'var(--fw-primary)' : 'var(--fw-success)',
                                        border: `1px solid ${u.role === 'admin' ? 'var(--fw-primary)' : 'var(--fw-success)'}`
                                    }}>
                                        {u.role === 'admin' ? '[ АДМІН ]' : '[ ЮЗЕР ]'}
                                    </span>
                                </td>
                                <td style={{ padding: '14px 20px', fontSize: '14px', color: 'var(--fw-text-muted)' }}>
                                    {u.description || '—'}
                                </td>
                                <td style={{ padding: '14px 20px', textAlign: 'center' }}>
                                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                                        <input
                                            type="text"
                                            className="input-field"
                                            defaultValue={u.allowed_ip}
                                            onBlur={(e) => {
                                                if (e.target.value !== u.allowed_ip) {
                                                    handleUpdateIp(u.id, e.target.value);
                                                }
                                            }}
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter') {
                                                    e.currentTarget.blur();
                                                }
                                            }}
                                            placeholder="*"
                                            style={{ width: '140px', padding: '6px 10px', fontSize: '13px', textAlign: 'center', fontWeight: 'bold' }}
                                            title="Дозволений IP або підмережа (напр. 192.168.1.* або *)"
                                        />
                                        <span style={{ fontSize: '11px', color: 'var(--fw-text-dim)', whiteSpace: 'nowrap' }}>
                                            Останній: {u.last_ip || 'Нема даних'}
                                        </span>
                                    </div>
                                </td>
                                <td style={{ padding: '14px 20px', textAlign: 'right' }}>
                                    <button
                                        onClick={() => handleDelete(u.id, u.username)}
                                        style={{
                                            padding: '6px 14px',
                                            borderRadius: '6px',
                                            border: '1px solid rgba(239,68,68,0.3)',
                                            background: 'rgba(239,68,68,0.1)',
                                            color: '#ef4444',
                                            cursor: 'pointer',
                                            fontSize: '13px',
                                        }}
                                    >
                                        🗑️ Видалити
                                    </button>
                                </td>
                            </tr>
                        ))}
                        {users.length === 0 && (
                            <tr>
                                <td colSpan={5} style={{ padding: '40px', textAlign: 'center', color: 'var(--fw-text-dim)', fontSize: '15px' }}>
                                    Немає користувачів
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div >
    );
}
