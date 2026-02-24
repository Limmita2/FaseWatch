import { useState, useEffect } from 'react';
import { inputApi, groupsApi } from '@/services/api';

interface GroupOption {
    id: string;
    name: string;
}

export default function InputPage() {
    const [photo, setPhoto] = useState<File | null>(null);
    const [preview, setPreview] = useState<string | null>(null);
    const [text, setText] = useState('');
    const [groupName, setGroupName] = useState('Ручной ввод');
    const [groupId, setGroupId] = useState('');
    const [groups, setGroups] = useState<GroupOption[]>([]);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<any>(null);
    const [error, setError] = useState('');

    useEffect(() => {
        groupsApi.list().then(res => setGroups(res.data)).catch(() => { });
    }, []);

    const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            setPhoto(file);
            setPreview(URL.createObjectURL(file));
        }
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            setPhoto(file);
            setPreview(URL.createObjectURL(file));
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!photo) return setError('Выберите фото');
        setLoading(true);
        setError('');
        setResult(null);
        try {
            const res = await inputApi.upload(photo, text, groupName, groupId);
            setResult(res.data);
            setPhoto(null);
            setPreview(null);
            setText('');
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Ошибка загрузки');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="animate-fade-in" style={{ maxWidth: '100%' }}>
            <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '24px' }}>📷 Ввод фото для распознавания</h1>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                {/* Левая колонка — загрузка */}
                <div className="glass-card" style={{ padding: '28px' }}>
                    <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '20px' }}>Загрузка фото</h2>

                    <div
                        onDrop={handleDrop}
                        onDragOver={e => e.preventDefault()}
                        onClick={() => document.getElementById('photo-input')?.click()}
                        style={{
                            border: '2px dashed rgba(255,255,255,0.2)',
                            borderRadius: '12px',
                            padding: preview ? '16px' : '48px 24px',
                            textAlign: 'center',
                            cursor: 'pointer',
                            transition: 'all 0.2s',
                            background: 'rgba(255,255,255,0.03)',
                            marginBottom: '20px',
                            minHeight: '200px',
                            display: 'flex',
                            flexDirection: 'column' as const,
                            alignItems: 'center',
                            justifyContent: 'center',
                        }}
                    >
                        <input
                            id="photo-input"
                            type="file"
                            accept="image/*"
                            onChange={handlePhotoChange}
                            style={{ display: 'none' }}
                        />
                        {preview ? (
                            <img src={preview} alt="Превью" style={{ maxWidth: '100%', maxHeight: '400px', borderRadius: '8px' }} />
                        ) : (
                            <>
                                <div style={{ fontSize: '48px', marginBottom: '12px' }}>📸</div>
                                <p style={{ fontSize: '16px', fontWeight: 500, marginBottom: '8px' }}>Перетащите фото сюда</p>
                                <p style={{ fontSize: '13px', color: 'var(--fw-text-dim)' }}>или нажмите для выбора файла</p>
                            </>
                        )}
                    </div>

                    {photo && (
                        <p style={{ fontSize: '13px', color: 'var(--fw-text-muted)', marginBottom: '8px' }}>
                            📄 {photo.name} ({(photo.size / 1024).toFixed(0)} KB)
                        </p>
                    )}
                </div>

                {/* Правая колонка — форма */}
                <div className="glass-card" style={{ padding: '28px' }}>
                    <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '20px' }}>Параметры</h2>

                    <form onSubmit={handleSubmit}>
                        <div style={{ marginBottom: '20px' }}>
                            <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--fw-text-muted)' }}>
                                Группа
                            </label>
                            <select
                                className="input-field"
                                value={groupId}
                                onChange={e => {
                                    setGroupId(e.target.value);
                                    const g = groups.find(g => g.id === e.target.value);
                                    if (g) setGroupName(g.name);
                                    else setGroupName('Ручной ввод');
                                }}
                                style={{ width: '100%', padding: '10px 14px', fontSize: '15px' }}
                            >
                                <option value="">📁 Ручной ввод (новая группа)</option>
                                {groups.map(g => (
                                    <option key={g.id} value={g.id}>{g.name}</option>
                                ))}
                            </select>
                        </div>

                        <div style={{ marginBottom: '20px' }}>
                            <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--fw-text-muted)' }}>
                                Описание / текст сообщения
                            </label>
                            <textarea
                                className="input-field"
                                value={text}
                                onChange={e => setText(e.target.value)}
                                rows={5}
                                placeholder="Введите описание фото (необязательно)"
                                style={{ width: '100%', padding: '10px 14px', fontSize: '15px', resize: 'vertical', minHeight: '120px' }}
                            />
                        </div>

                        {error && (
                            <div style={{ padding: '12px 16px', borderRadius: '8px', background: 'rgba(239,68,68,0.15)', color: '#ef4444', marginBottom: '16px', fontSize: '14px' }}>
                                ⚠️ {error}
                            </div>
                        )}

                        <button
                            type="submit"
                            className="btn-primary"
                            disabled={loading || !photo}
                            style={{
                                width: '100%',
                                padding: '14px 24px',
                                fontSize: '16px',
                                fontWeight: 600,
                                opacity: loading || !photo ? 0.5 : 1,
                            }}
                        >
                            {loading ? '⏳ Загрузка...' : '📤 Загрузить и обработать лица'}
                        </button>
                    </form>
                </div>
            </div>

            {result && (
                <div className="glass-card" style={{ marginTop: '24px', padding: '24px' }}>
                    <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', color: '#22c55e' }}>✅ Фото загружено и отправлено на обработку</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
                        <div>
                            <span style={{ fontSize: '13px', color: 'var(--fw-text-dim)' }}>Группа</span>
                            <p style={{ fontSize: '15px', fontWeight: 500 }}>{result.group_name}</p>
                        </div>
                        <div>
                            <span style={{ fontSize: '13px', color: 'var(--fw-text-dim)' }}>Текст</span>
                            <p style={{ fontSize: '15px', fontWeight: 500 }}>{result.text || '—'}</p>
                        </div>
                        <div>
                            <span style={{ fontSize: '13px', color: 'var(--fw-text-dim)' }}>Обработка лиц</span>
                            <p style={{ fontSize: '15px', fontWeight: 500, color: '#f59e0b' }}>🔄 В очереди Celery</p>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
