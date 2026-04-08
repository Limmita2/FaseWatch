import { NavLink, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';

export default function Sidebar() {
    const { role, logout } = useAuthStore();
    const navigate = useNavigate();

    const navItems = [
        { path: '/', label: 'Дашборд', icon: '📊', adminOnly: false },
        { path: '/search', label: 'Пошук', icon: '🔍', adminOnly: false },
        { path: '/ai', label: 'AI', icon: '🤖', adminOnly: true },
        { path: '/ai/reports', label: 'Звіти AI', icon: '🧾', adminOnly: true },
        { path: '/input', label: 'Введення', icon: '📷', adminOnly: true },
        { path: '/messages', label: 'Повідомлення', icon: '💬', adminOnly: true },
        { path: '/groups', label: 'Групи', icon: '👥', adminOnly: true },
        { path: '/tg-accounts', label: 'Telegram', icon: 'tg', adminOnly: true },
        { path: '/wa-accounts', label: 'WhatsApp', icon: 'wa', adminOnly: true },
        { path: '/signal', label: 'Signal', icon: 'signal', adminOnly: true },
        { path: '/import', label: 'Імпорт', icon: '📦', adminOnly: true },
        { path: '/users', label: 'Користувачі', icon: '⚙️', adminOnly: true },
    ];

    const renderIcon = (icon: string) => {
        if (icon === 'tg') {
            return (
                <svg className="nav-icon" viewBox="0 0 24 24" width="18" height="18" fill="none">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" fill="#2AABEE"/>
                    <path d="M16.5 8.3c-.1-.1-.3-.2-.5-.1L6.8 11.8c-.4.2-.4.5-.1.7l2.4.8 1.1 3.5c.1.3.5.4.7.2l1.6-1.4 3.1 2.3c.3.2.7.1.8-.3l2.4-11.3c.1-.4-.1-.7-.4-.7zM9.4 13.4l-.4 3.3-.9-2.9 6.8-4.3-5.5 3.9z" fill="white"/>
                </svg>
            );
        }
        if (icon === 'wa') {
            return (
                <svg className="nav-icon" viewBox="0 0 24 24" width="18" height="18" fill="none">
                    <path d="M12 2C6.48 2 2 6.48 2 12c0 1.82.49 3.53 1.34 5L2 22l5.13-1.33A9.96 9.96 0 0012 22c5.52 0 10-4.48 10-10S17.52 2 12 2z" fill="#25D366"/>
                    <path d="M17.5 14.4c-.2-.1-1.2-.6-1.4-.7-.2-.1-.3-.1-.5.1-.1.2-.6.7-.7.8-.1.1-.3.2-.5.1-.2-.1-.8-.3-1.6-1-.6-.5-1-1.2-1.1-1.4-.1-.2 0-.3.1-.5.1-.1.2-.3.3-.4.1-.1.1-.2.2-.4 0-.2 0-.3-.1-.5-.1-.2-.5-1.2-.7-1.6-.2-.4-.4-.4-.5-.4h-.5c-.2 0-.4.1-.6.3-.2.2-.7.7-.7 1.7s.7 2 .8 2.1c.1.1 1.4 2.1 3.3 2.9.5.2.8.3 1.1.4.5.2.9.1 1.2.1.4 0 1.2-.5 1.4-.9.2-.4.2-.8.1-.9-.1-.1-.2-.2-.4-.3z" fill="white"/>
                </svg>
            );
        }
        if (icon === 'signal') {
            return (
                <svg className="nav-icon" viewBox="0 0 24 24" width="18" height="18" fill="none">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" fill="#3A76F0"/>
                    <circle cx="12" cy="12" r="2" fill="white"/>
                    <path d="M12 6a6 6 0 00-6 6h2a4 4 0 018 0h2a6 6 0 00-6-6z" fill="white" opacity="0.7"/>
                    <path d="M12 2a10 10 0 00-10 10h2a8 8 0 0116 0h2A10 10 0 0012 2z" fill="white" opacity="0.4"/>
                </svg>
            );
        }
        return <span className="nav-icon" style={{ fontSize: '18px' }}>{icon}</span>;
    };

    const visibleItems = navItems.filter(item => !item.adminOnly || role === 'admin');

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    return (
        <aside className="sidebar">
            <div className="sidebar-logo" style={{ marginBottom: '40px' }}>
                <span style={{ fontSize: '24px', letterSpacing: '4px' }}>FACEWATCH</span>
            </div>
            <nav className="sidebar-nav">
                {visibleItems.map(item => (
                    <NavLink
                        key={item.path}
                        to={item.path}
                        end={item.path === '/'}
                        className={({ isActive }) =>
                            `nav-link ${isActive ? 'active' : ''}`
                        }
                    >
                        {renderIcon(item.icon)}
                        <span className="nav-label" style={{ textTransform: 'uppercase', letterSpacing: '1px' }}>{item.label}</span>
                    </NavLink>
                ))}
            </nav>
            <div className="sidebar-footer" style={{ marginTop: 'auto', paddingTop: '24px', borderTop: '1px solid var(--fw-border)', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <span className="badge badge-primary" style={{ alignSelf: 'flex-start' }}>{role === 'admin' ? 'АДМІНІСТРАТОР' : 'ОПЕРАТОР'}</span>
                <button onClick={handleLogout} className="btn-secondary" style={{ width: '100%' }}>[ ВІДКЛЮЧИТИСЯ ]</button>
            </div>
        </aside>
    );
}
