import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '@/services/api';
import { useAuthStore } from '@/store/authStore';

export default function LoginPage() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const { login } = useAuthStore();
    const navigate = useNavigate();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            const { data } = await authApi.login(username, password);
            login(data.access_token, data.role);
            navigate('/');
        } catch {
            setError('Неверный логин или пароль');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%)',
        }}>
            <div className="glass-card animate-slide-up" style={{
                width: '100%',
                maxWidth: '420px',
                padding: '40px',
            }}>
                <div style={{ textAlign: 'center', marginBottom: '32px' }}>
                    <div style={{ fontSize: '48px', marginBottom: '12px' }}>👁️</div>
                    <h1 style={{
                        fontSize: '28px',
                        fontWeight: 700,
                        background: 'linear-gradient(135deg, var(--fw-primary), var(--fw-accent))',
                        WebkitBackgroundClip: 'text',
                        WebkitTextFillColor: 'transparent',
                    }}>FaceWatch</h1>
                    <p style={{ color: 'var(--fw-text-muted)', marginTop: '8px', fontSize: '14px' }}>
                        Система мониторинга з розпізнаванням облич
                    </p>
                </div>

                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div>
                        <label style={{ display: 'block', fontSize: '13px', color: 'var(--fw-text-muted)', marginBottom: '6px' }}>
                            Логін
                        </label>
                        <input
                            className="input-field"
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            placeholder="admin"
                            required
                        />
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: '13px', color: 'var(--fw-text-muted)', marginBottom: '6px' }}>
                            Пароль
                        </label>
                        <input
                            className="input-field"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="••••••••"
                            required
                        />
                    </div>

                    {error && (
                        <div style={{
                            background: 'rgba(255, 71, 87, 0.1)',
                            border: '1px solid rgba(255, 71, 87, 0.3)',
                            borderRadius: 'var(--fw-radius-sm)',
                            padding: '10px',
                            fontSize: '13px',
                            color: 'var(--fw-danger)',
                        }}>
                            {error}
                        </div>
                    )}

                    <button className="btn-primary" type="submit" disabled={loading} style={{ marginTop: '8px', padding: '12px' }}>
                        {loading ? <span className="spinner" style={{ width: 18, height: 18, margin: '0 auto' }} /> : 'Увійти'}
                    </button>
                </form>

                <p style={{ textAlign: 'center', color: 'var(--fw-text-dim)', fontSize: '12px', marginTop: '24px' }}>
                    За замовчуванням: admin / admin
                </p>
            </div>
        </div>
    );
}
