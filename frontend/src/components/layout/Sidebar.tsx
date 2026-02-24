import { NavLink, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';

export default function Sidebar() {
    const { role, logout } = useAuthStore();
    const navigate = useNavigate();

    const navItems = [
        { path: '/', label: 'Дашборд', icon: '📊', adminOnly: false },
        { path: '/search', label: 'Поиск', icon: '🔍', adminOnly: false },
        { path: '/input', label: 'Ввод', icon: '📷', adminOnly: true },
        { path: '/messages', label: 'Сообщения', icon: '💬', adminOnly: true },
        { path: '/persons', label: 'Персоны', icon: '👤', adminOnly: true },
        { path: '/groups', label: 'Группы', icon: '👥', adminOnly: true },
        { path: '/import', label: 'Импорт', icon: '📦', adminOnly: true },
        { path: '/users', label: 'Пользователи', icon: '⚙️', adminOnly: true },
    ];

    const visibleItems = navItems.filter(item => !item.adminOnly || role === 'admin');

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    return (
        <aside className="sidebar">
            <div className="sidebar-header">
                <h2>FaseWatch</h2>
            </div>
            <nav className="sidebar-nav">
                {visibleItems.map(item => (
                    <NavLink
                        key={item.path}
                        to={item.path}
                        end={item.path === '/'}
                        className={({ isActive }) =>
                            `nav-item ${isActive ? 'active' : ''}`
                        }
                    >
                        <span className="nav-icon">{item.icon}</span>
                        <span className="nav-label">{item.label}</span>
                    </NavLink>
                ))}
            </nav>
            <div className="sidebar-footer">
                <span className="role-badge">{role === 'admin' ? 'Админ' : 'Оператор'}</span>
                <button onClick={handleLogout} className="logout-btn">Выйти</button>
            </div>
        </aside>
    );
}
