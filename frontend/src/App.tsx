import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import AppLayout from '@/components/layout/AppLayout';
import LoginPage from '@/pages/LoginPage';
import DashboardPage from '@/pages/DashboardPage';
import MessagesPage from '@/pages/MessagesPage';
import SearchPage from '@/pages/SearchPage';
import PersonsPage from '@/pages/PersonsPage';
import QueuePage from '@/pages/QueuePage';
import GroupsPage from '@/pages/GroupsPage';
import ImportPage from '@/pages/ImportPage';
import UsersPage from '@/pages/UsersPage';
import InputPage from '@/pages/InputPage';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
    const { isLoggedIn } = useAuthStore();
    return isLoggedIn ? <>{children}</> : <Navigate to="/login" replace />;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
    const { role } = useAuthStore();
    return role === 'admin' ? <>{children}</> : <Navigate to="/" replace />;
}

export default function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route
                    element={
                        <ProtectedRoute>
                            <AppLayout />
                        </ProtectedRoute>
                    }
                >
                    <Route index element={<DashboardPage />} />
                    <Route path="search" element={<SearchPage />} />
                    {/* Admin-only routes */}
                    <Route path="messages" element={<AdminRoute><MessagesPage /></AdminRoute>} />
                    <Route path="persons" element={<AdminRoute><PersonsPage /></AdminRoute>} />
                    <Route path="queue" element={<AdminRoute><QueuePage /></AdminRoute>} />
                    <Route path="groups" element={<AdminRoute><GroupsPage /></AdminRoute>} />
                    <Route path="import" element={<AdminRoute><ImportPage /></AdminRoute>} />
                    <Route path="users" element={<AdminRoute><UsersPage /></AdminRoute>} />
                    <Route path="input" element={<AdminRoute><InputPage /></AdminRoute>} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </BrowserRouter>
    );
}
