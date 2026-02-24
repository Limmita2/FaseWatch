import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

const api = axios.create({
    baseURL: `${API_BASE}/api`,
});

// Добавляем JWT токен ко всем запросам
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Перенаправляем на логин при 401
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            localStorage.removeItem('token');
            window.location.href = '/login';
        }
        return Promise.reject(error);
    }
);

export default api;

// ===== Auth =====
export const authApi = {
    login: (username: string, password: string) =>
        api.post('/auth/login', new URLSearchParams({ username, password }), {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        }),
};

// ===== Dashboard =====
export const dashboardApi = {
    get: () => api.get('/dashboard'),
};

// ===== Messages =====
export const messagesApi = {
    list: (params?: Record<string, string | number | boolean>) => api.get('/messages/', { params }),
    context: (id: string) => api.get(`/messages/${id}/context`),
    delete: (id: string) => api.delete(`/messages/${id}`),
};

// ===== Persons =====
export const personsApi = {
    list: () => api.get('/persons/'),
    get: (id: string) => api.get(`/persons/${id}`),
    update: (id: string, data: { display_name?: string; confirmed?: boolean }) =>
        api.patch(`/persons/${id}`, data),
    merge: (sourceId: string, targetId: string) =>
        api.post('/persons/merge', { source_person_id: sourceId, target_person_id: targetId }),
    delete: (id: string) => api.delete(`/persons/${id}`),
};

// ===== Search =====
export const searchApi = {
    byFace: (photo: File, topK = 5, threshold = 50, faceIndex?: number) => {
        const fd = new FormData();
        fd.append('photo', photo);
        let url = `/search/face?top_k=${topK}&threshold=${threshold}`;
        if (faceIndex !== undefined) url += `&face_index=${faceIndex}`;
        return api.post(url, fd);
    },
    byText: (q: string, page = 1) => api.get('/search/text', { params: { q, page } }),
};

// ===== Queue =====
export const queueApi = {
    list: () => api.get('/queue/'),
    confirm: (id: string) => api.post(`/queue/${id}/confirm`),
    reject: (id: string) => api.post(`/queue/${id}/reject`),
};

// ===== Groups =====
export const groupsApi = {
    list: () => api.get('/groups/'),
    delete: (id: string) => api.delete(`/groups/${id}`),
};

// ===== Import =====
export const importApi = {
    upload: (file: File, groupName: string, groupId?: string) => {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('group_name', groupName);
        if (groupId) fd.append('group_id', groupId);
        return api.post('/import/', fd);
    },
};

// ===== Users =====
export const usersApi = {
    list: () => api.get('/users/'),
    create: (data: { username: string; password: string; role: string; description?: string }) =>
        api.post('/users/', data),
    delete: (id: string) => api.delete(`/users/${id}`),
};

// ===== Input =====
export const inputApi = {
    upload: (photo: File, text: string, groupName?: string, groupId?: string) => {
        const fd = new FormData();
        fd.append('photo', photo);
        fd.append('text', text);
        if (groupName) fd.append('group_name', groupName);
        if (groupId) fd.append('group_id', groupId);
        return api.post('/input/', fd);
    },
};
