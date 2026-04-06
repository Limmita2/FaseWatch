import { useEffect, useState } from 'react';

import { groupsApi, tgAccountsApi } from '@/services/api';

interface TelegramAccount {
    id: string;
    name: string;
    region?: string;
    phone: string;
    status: string;
    is_active: boolean;
    created_at?: string;
}

interface GroupOption {
    id: string;
    name: string;
    telegram_id?: number | null;
}

interface AccountGroup {
    id: string;
    group_id: string;
    group_name: string;
    telegram_id?: number | null;
    history_loaded: boolean;
    history_load_progress: number;
    last_message_id?: number | null;
    is_active: boolean;
}

interface DiscoveredGroup {
    telegram_id: number;
    title: string;
    already_connected: boolean;
    group_id?: string | null;
}

const statusClassMap: Record<string, string> = {
    active: 'badge-success',
    pending_auth: 'badge-warning',
    error: 'badge-danger',
    disabled: 'badge-danger',
};

function getPipelineStatus(group: AccountGroup) {
    if (!group.is_active) {
        return { label: 'DISABLED', className: 'badge-danger' };
    }
    if (group.telegram_id == null || group.telegram_id >= 0) {
        return { label: 'INVALID ID', className: 'badge-danger' };
    }
    if (!group.history_loaded) {
        return { label: 'HISTORY', className: 'badge-warning' };
    }
    return { label: 'LIVE', className: 'badge-success' };
}

export default function TgAccountsPage() {
    const [accounts, setAccounts] = useState<TelegramAccount[]>([]);
    const [accountGroups, setAccountGroups] = useState<Record<string, AccountGroup[]>>({});
    const [discoveredGroups, setDiscoveredGroups] = useState<Record<string, DiscoveredGroup[]>>({});
    const [expandedAccountId, setExpandedAccountId] = useState<string | null>(null);
    const [pendingAuthId, setPendingAuthId] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [createForm, setCreateForm] = useState({
        name: '',
        region: '',
        phone: '',
        api_id: '',
        api_hash: '',
    });
    const [verifyForm, setVerifyForm] = useState({
        code: '',
        password: '',
    });

    const fetchAccounts = async () => {
        try {
            const accountsRes = await tgAccountsApi.list();
            setAccounts(accountsRes.data);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося завантажити Telegram-акаунти');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAccounts();
    }, []);

    const clearMessages = () => {
        setError('');
        setSuccess('');
    };

    const loadAccountGroups = async (accountId: string) => {
        try {
            const res = await tgAccountsApi.groups(accountId);
            setAccountGroups(prev => ({ ...prev, [accountId]: res.data }));
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося завантажити групи акаунту');
        }
    };

    const loadDiscoveredGroups = async (accountId: string) => {
        try {
            const res = await tgAccountsApi.discoverGroups(accountId);
            setDiscoveredGroups(prev => ({ ...prev, [accountId]: res.data }));
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося отримати список доступних груп акаунту');
        }
    };

    const toggleExpanded = async (accountId: string) => {
        clearMessages();
        const nextValue = expandedAccountId === accountId ? null : accountId;
        setExpandedAccountId(nextValue);
        if (nextValue) {
            await Promise.all([
                loadAccountGroups(accountId),
                loadDiscoveredGroups(accountId),
            ]);
        }
    };

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        clearMessages();
        setSaving(true);
        try {
            const res = await tgAccountsApi.create({
                ...createForm,
                region: createForm.region || undefined,
            });
            setCreateForm({ name: '', region: '', phone: '', api_id: '', api_hash: '' });
            setPendingAuthId(res.data.id);
            setSuccess('Акаунт створено. Тепер надішліть код підтвердження.');
            await fetchAccounts();
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося створити акаунт');
        } finally {
            setSaving(false);
        }
    };

    const handleSendCode = async (accountId: string) => {
        clearMessages();
        setSaving(true);
        try {
            await tgAccountsApi.sendCode(accountId);
            setPendingAuthId(accountId);
            setSuccess('Код авторизації відправлено.');
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося надіслати код');
        } finally {
            setSaving(false);
        }
    };

    const handleVerify = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!pendingAuthId) return;
        clearMessages();
        setSaving(true);
        try {
            await tgAccountsApi.verifyCode(pendingAuthId, {
                code: verifyForm.code,
                password: verifyForm.password || undefined,
            });
            setVerifyForm({ code: '', password: '' });
            setPendingAuthId(null);
            setSuccess('Акаунт авторизовано.');
            await fetchAccounts();
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося підтвердити код');
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (accountId: string, accountName: string) => {
        if (!confirm(`Відключити акаунт "${accountName}"?`)) return;
        clearMessages();
        try {
            await tgAccountsApi.delete(accountId);
            setSuccess('Акаунт деактивовано.');
            if (expandedAccountId === accountId) {
                setExpandedAccountId(null);
            }
            await fetchAccounts();
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося деактивувати акаунт');
        }
    };

    const handleAddGroup = async (accountId: string, telegramId: number, groupName: string) => {
        clearMessages();
        try {
            await tgAccountsApi.addGroup(accountId, { telegram_group_id: telegramId, group_name: groupName });
            setSuccess('Групу підключено.');
            await Promise.all([
                loadAccountGroups(accountId),
                loadDiscoveredGroups(accountId),
            ]);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося підключити групу');
        }
    };

    const handleRemoveGroup = async (accountId: string, groupId: string) => {
        if (!confirm('Відключити групу від акаунту?')) return;
        clearMessages();
        try {
            await tgAccountsApi.removeGroup(accountId, groupId);
            setSuccess('Групу відключено.');
            await Promise.all([
                loadAccountGroups(accountId),
                loadDiscoveredGroups(accountId),
            ]);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося відключити групу');
        }
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
                    [ TELEGRAM АКАУНТИ ]
                </h1>
                <span className="badge badge-primary">АКАУНТІВ: {accounts.length}</span>
            </div>

            {error && (
                <div style={{ padding: '12px 16px', borderRadius: '8px', background: 'rgba(239,68,68,0.15)', color: '#ef4444', fontSize: '14px' }}>
                    {error}
                </div>
            )}
            {success && (
                <div style={{ padding: '12px 16px', borderRadius: '8px', background: 'rgba(34,197,94,0.15)', color: '#22c55e', fontSize: '14px' }}>
                    {success}
                </div>
            )}

            <div className="glass-card" style={{ overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <th style={{ padding: '14px 18px', textAlign: 'left' }}>НАЗВА</th>
                            <th style={{ padding: '14px 18px', textAlign: 'left' }}>РЕГІОН</th>
                            <th style={{ padding: '14px 18px', textAlign: 'left' }}>ТЕЛЕФОН</th>
                            <th style={{ padding: '14px 18px', textAlign: 'left' }}>СТАТУС</th>
                            <th style={{ padding: '14px 18px', textAlign: 'right' }}>ДІЇ</th>
                        </tr>
                    </thead>
                    <tbody>
                        {accounts.map(account => (
                            <tr key={account.id} style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                                <td style={{ padding: '16px 18px', fontWeight: 600 }}>{account.name}</td>
                                <td style={{ padding: '16px 18px', color: 'var(--fw-text-muted)' }}>{account.region || '—'}</td>
                                <td style={{ padding: '16px 18px', fontFamily: 'monospace' }}>{account.phone}</td>
                                <td style={{ padding: '16px 18px' }}>
                                    <span className={`badge ${statusClassMap[account.status] || 'badge-primary'}`}>{account.status}</span>
                                </td>
                                <td style={{ padding: '16px 18px', textAlign: 'right' }}>
                                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', flexWrap: 'wrap' }}>
                                        <button className="btn-secondary" onClick={() => toggleExpanded(account.id)}>Групи</button>
                                        {account.status !== 'active' && account.is_active && (
                                            <button className="btn-primary" onClick={() => handleSendCode(account.id)} disabled={saving}>
                                                Код
                                            </button>
                                        )}
                                        <button className="btn-danger" onClick={() => handleDelete(account.id, account.name)}>
                                            Видалити
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                        {accounts.length === 0 && (
                            <tr>
                                <td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: 'var(--fw-text-dim)' }}>
                                    Акаунтів поки немає
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {expandedAccountId && (
                <div className="glass-card" style={{ padding: '24px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', gap: '12px', flexWrap: 'wrap' }}>
                        <h2 style={{ fontSize: '18px', fontWeight: 700 }}>Групи акаунту</h2>
                        <button className="btn-secondary" onClick={() => Promise.all([loadAccountGroups(expandedAccountId), loadDiscoveredGroups(expandedAccountId)])}>Оновити</button>
                    </div>

                    <div className="glass-card" style={{ padding: '18px', marginBottom: '18px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', gap: '12px', flexWrap: 'wrap' }}>
                            <h3 style={{ fontSize: '16px', fontWeight: 700 }}>Доступні групи акаунту</h3>
                            <button className="btn-secondary" onClick={() => loadDiscoveredGroups(expandedAccountId)}>Сканувати групи</button>
                        </div>

                        <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '12px' }}>
                            <thead>
                                <tr>
                                    <th style={{ padding: '12px 0', textAlign: 'left' }}>НАЗВА</th>
                                    <th style={{ padding: '12px 0', textAlign: 'left' }}>TG ID</th>
                                    <th style={{ padding: '12px 0', textAlign: 'left' }}>СТАТУС</th>
                                    <th style={{ padding: '12px 0', textAlign: 'right' }}>ДІЯ</th>
                                </tr>
                            </thead>
                            <tbody>
                                {(discoveredGroups[expandedAccountId] || []).map(group => (
                                    <tr key={group.telegram_id} style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                                        <td style={{ padding: '14px 0' }}>{group.title}</td>
                                        <td style={{ padding: '14px 0', fontFamily: 'monospace', color: 'var(--fw-text-muted)' }}>{group.telegram_id}</td>
                                        <td style={{ padding: '14px 0' }}>
                                            <span className={`badge ${group.already_connected ? 'badge-success' : 'badge-warning'}`}>
                                                {group.already_connected ? 'ПІДКЛЮЧЕНО' : 'ОЧІКУЄ ВИБОРУ'}
                                            </span>
                                        </td>
                                        <td style={{ padding: '14px 0', textAlign: 'right' }}>
                                            {group.already_connected ? (
                                                <span style={{ color: 'var(--fw-text-dim)', fontSize: '13px' }}>Вже в роботі</span>
                                            ) : (
                                                <button className="btn-primary" onClick={() => handleAddGroup(expandedAccountId, group.telegram_id, group.title)}>
                                                    Підключити
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                                {(discoveredGroups[expandedAccountId] || []).length === 0 && (
                                    <tr>
                                        <td colSpan={4} style={{ padding: '20px 0', color: 'var(--fw-text-dim)', textAlign: 'center' }}>
                                            Список груп ще не завантажено або в акаунта немає доступних груп
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                        <div style={{ color: 'var(--fw-text-muted)', fontSize: '13px' }}>
                            Сервіс почне працювати тільки з тими групами, які ти явно підключиш.
                        </div>
                    </div>

                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr>
                                <th style={{ padding: '12px 0', textAlign: 'left' }}>ГРУПА</th>
                                <th style={{ padding: '12px 0', textAlign: 'left' }}>TG ID</th>
                                <th style={{ padding: '12px 0', textAlign: 'left' }}>ЕТАП</th>
                                <th style={{ padding: '12px 0', textAlign: 'left' }}>ПРОГРЕС</th>
                                <th style={{ padding: '12px 0', textAlign: 'left' }}>ОСТАННЄ MSG ID</th>
                                <th style={{ padding: '12px 0', textAlign: 'right' }}>ДІЇ</th>
                            </tr>
                        </thead>
                        <tbody>
                            {(accountGroups[expandedAccountId] || []).map(group => {
                                const pipelineStatus = getPipelineStatus(group);
                                return (
                                    <tr key={group.id} style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                                        <td style={{ padding: '14px 0' }}>{group.group_name}</td>
                                        <td style={{ padding: '14px 0', fontFamily: 'monospace', color: 'var(--fw-text-muted)' }}>
                                            {group.telegram_id ?? '—'}
                                        </td>
                                        <td style={{ padding: '14px 0' }}>
                                            <span className={`badge ${pipelineStatus.className}`}>
                                                {pipelineStatus.label}
                                            </span>
                                        </td>
                                        <td style={{ padding: '14px 0' }}>
                                            <span className={`badge ${group.history_loaded ? 'badge-success' : 'badge-warning'}`}>
                                                {group.history_loaded ? `Готово (${group.history_load_progress})` : `Завантажено ${group.history_load_progress}`}
                                            </span>
                                        </td>
                                        <td style={{ padding: '14px 0', fontFamily: 'monospace', color: 'var(--fw-text-muted)' }}>
                                            {group.last_message_id ?? '—'}
                                        </td>
                                        <td style={{ padding: '14px 0', textAlign: 'right' }}>
                                            <button className="btn-danger" onClick={() => handleRemoveGroup(expandedAccountId, group.group_id)}>
                                                Відключити
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}
                            {(accountGroups[expandedAccountId] || []).length === 0 && (
                                <tr>
                                    <td colSpan={6} style={{ padding: '20px 0', color: 'var(--fw-text-dim)', textAlign: 'center' }}>
                                        Для цього акаунту ще немає груп
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: pendingAuthId ? '1.3fr 1fr' : '1fr', gap: '24px' }}>
                <div className="glass-card" style={{ padding: '24px' }}>
                    <h2 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '18px' }}>Новий акаунт</h2>
                    <form onSubmit={handleCreate}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                            <input className="input-field" placeholder="Псевдонім" value={createForm.name} onChange={(e) => setCreateForm(prev => ({ ...prev, name: e.target.value }))} required />
                            <input className="input-field" placeholder="Регіон" value={createForm.region} onChange={(e) => setCreateForm(prev => ({ ...prev, region: e.target.value }))} />
                            <input className="input-field" placeholder="+380XXXXXXXXX" value={createForm.phone} onChange={(e) => setCreateForm(prev => ({ ...prev, phone: e.target.value }))} required />
                            <input className="input-field" placeholder="API ID" value={createForm.api_id} onChange={(e) => setCreateForm(prev => ({ ...prev, api_id: e.target.value }))} required />
                        </div>
                        <div style={{ marginBottom: '18px' }}>
                            <input className="input-field" placeholder="API Hash" value={createForm.api_hash} onChange={(e) => setCreateForm(prev => ({ ...prev, api_hash: e.target.value }))} required />
                        </div>
                        <button className="btn-primary" type="submit" disabled={saving}>
                            Створити акаунт
                        </button>
                    </form>
                </div>

                {pendingAuthId && (
                    <div className="glass-card" style={{ padding: '24px' }}>
                        <h2 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '18px' }}>Підтвердження коду</h2>
                        <form onSubmit={handleVerify}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                                <input className="input-field" placeholder="Код із Telegram" value={verifyForm.code} onChange={(e) => setVerifyForm(prev => ({ ...prev, code: e.target.value }))} required />
                                <input className="input-field" placeholder="2FA пароль (якщо є)" value={verifyForm.password} onChange={(e) => setVerifyForm(prev => ({ ...prev, password: e.target.value }))} />
                                <button className="btn-success" type="submit" disabled={saving}>
                                    Підтвердити
                                </button>
                            </div>
                        </form>
                    </div>
                )}
            </div>
        </div>
    );
}
