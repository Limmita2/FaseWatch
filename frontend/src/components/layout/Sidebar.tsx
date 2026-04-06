import { NavLink, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';

export default function Sidebar() {
    const { role, logout } = useAuthStore();
    const navigate = useNavigate();

    const navItems = [
        { path: '/', label: 'Дашборд', icon: '📊', adminOnly: false },
        { path: '/search', label: 'Пошук', icon: '🔍', adminOnly: false },
        { path: '/ai', label: 'AI', icon: '🤖', adminOnly: false },
        { path: '/ai/reports', label: 'Звіти AI', icon: '🧾', adminOnly: false },
        { path: '/input', label: 'Введення', icon: '📷', adminOnly: true },
        { path: '/messages', label: 'Повідомлення', icon: '💬', adminOnly: true },
        { path: '/groups', label: 'Групи', icon: '👥', adminOnly: true },
        { path: '/tg-accounts', label: 'Акаунти TG', icon: '📱', adminOnly: true },
        { path: '/import', label: 'Імпорт', icon: '📦', adminOnly: true },
        { path: '/users', label: 'Користувачі', icon: '⚙️', adminOnly: true },
    ];

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
                        <span className="nav-icon" style={{ fontSize: '18px' }}>{item.icon}</span>
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
