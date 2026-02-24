import { useState, useEffect } from 'react';
import { usersApi } from '@/services/api';

interface User {
    id: string;
    username: string;
    role: string;
    description?: string;
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
            setError('Ошибка загрузки пользователей');
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
            setSuccess('Пользователь создан');
            fetchUsers();
            setTimeout(() => setSuccess(''), 3000);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Ошибка создания пользователя');
        }
    };

    const handleDelete = async (id: string, username: string) => {
        if (!confirm(`Удалить пользователя "${username}"?`)) return;
        try {
            await usersApi.delete(id);
            setSuccess(`Пользователь "${username}" удалён`);
            fetchUsers();
            setTimeout(() => setSuccess(''), 3000);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Ошибка удаления');
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
                <h1 style={{ fontSize: '24px', fontWeight: 700 }}>⚙️ Управление пользователями</h1>
                <button
                    className={showForm ? 'btn-secondary' : 'btn-primary'}
                    onClick={() => { setShowForm(!showForm); setError(''); }}
                    style={{ padding: '10px 24px', fontSize: '15px' }}
                >
                    {showForm ? '✕ Отмена' : '+ Добавить пользователя'}
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
                    <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '20px' }}>Новый пользователь</h2>
                    <form onSubmit={handleCreate}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                            <div>
                                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--fw-text-muted)' }}>Логин *</label>
                                <input
                                    className="input-field"
                                    type="text"
                                    value={form.username}
                                    required
                                    placeholder="Введите логин"
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
                                    placeholder="Введите пароль"
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
                                    <option value="admin">Администратор</option>
                                </select>
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--fw-text-muted)' }}>Описание</label>
                                <input
                                    className="input-field"
                                    type="text"
                                    value={form.description}
                                    placeholder="Например: Оператор дежурной смены"
                                    onChange={e => setForm({ ...form, description: e.target.value })}
                                    style={{ width: '100%', padding: '10px 14px', fontSize: '15px' }}
                                />
                            </div>
                        </div>
                        <button type="submit" className="btn-primary" style={{ padding: '12px 32px', fontSize: '15px' }}>
                            ✅ Создать пользователя
                        </button>
                    </form>
                </div>
            )}

            <div className="glass-card" style={{ padding: '0', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ background: 'rgba(255,255,255,0.05)', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                            <th style={{ padding: '14px 20px', textAlign: 'left', fontSize: '13px', fontWeight: 600, color: 'var(--fw-text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Логин</th>
                            <th style={{ padding: '14px 20px', textAlign: 'left', fontSize: '13px', fontWeight: 600, color: 'var(--fw-text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Роль</th>
                            <th style={{ padding: '14px 20px', textAlign: 'left', fontSize: '13px', fontWeight: 600, color: 'var(--fw-text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Описание</th>
                            <th style={{ padding: '14px 20px', textAlign: 'right', fontSize: '13px', fontWeight: 600, color: 'var(--fw-text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', width: '100px' }}>Действия</th>
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
                                        borderRadius: '20px',
                                        fontSize: '12px',
                                        fontWeight: 600,
                                        background: u.role === 'admin' ? 'rgba(168,85,247,0.2)' : 'rgba(59,130,246,0.2)',
                                        color: u.role === 'admin' ? '#a855f7' : '#3b82f6',
                                    }}>
                                        {u.role === 'admin' ? '🔑 Админ' : '👁 Оператор'}
                                    </span>
                                </td>
                                <td style={{ padding: '14px 20px', fontSize: '14px', color: 'var(--fw-text-muted)' }}>
                                    {u.description || '—'}
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
                                        🗑️ Удалить
                                    </button>
                                </td>
                            </tr>
                        ))}
                        {users.length === 0 && (
                            <tr>
                                <td colSpan={4} style={{ padding: '40px', textAlign: 'center', color: 'var(--fw-text-dim)', fontSize: '15px' }}>
                                    Нет пользователей
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
