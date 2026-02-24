import { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { importApi, groupsApi } from '@/services/api';

export default function ImportPage() {
    const [groups, setGroups] = useState<any[]>([]);
    const [groupId, setGroupId] = useState('');
    const [newGroupName, setNewGroupName] = useState('');
    const [useExisting, setUseExisting] = useState(false);
    const [file, setFile] = useState<File | null>(null);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<any>(null);

    useEffect(() => {
        groupsApi.list().then(r => setGroups(r.data)).catch(() => { });
    }, []);

    const onDrop = useCallback((files: File[]) => {
        if (files.length) setFile(files[0]);
    }, []);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: { 'application/zip': ['.zip'] }, maxFiles: 1 });

    const handleImport = async () => {
        if (!file) return;
        setLoading(true);
        setResult(null);
        try {
            const { data } = await importApi.upload(file, useExisting ? '' : newGroupName, useExisting ? groupId : '');
            setResult(data);
        } catch (e: any) {
            setResult({ error: e.response?.data?.detail || 'Помилка імпорту' });
        }
        setLoading(false);
    };

    return (
        <div className="animate-fade-in">
            <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '24px' }}>📦 Імпорт резервної копії</h1>

            <div className="glass-card" style={{ padding: '24px', marginBottom: '20px' }}>
                <div {...getRootProps()} className={`dropzone ${isDragActive ? 'active' : ''}`}>
                    <input {...getInputProps()} />
                    {file ? (
                        <div>
                            <p style={{ fontSize: '16px', fontWeight: 500 }}>📄 {file.name}</p>
                            <p style={{ fontSize: '13px', color: 'var(--fw-text-muted)' }}>{(file.size / 1024 / 1024).toFixed(1)} МБ</p>
                        </div>
                    ) : (
                        <div>
                            <p style={{ fontSize: '16px', marginBottom: '8px' }}>📁 Перетягніть ZIP-архів сюди</p>
                            <p style={{ fontSize: '13px' }}>Формат: експорт Telegram Desktop (messages.html + photos/)</p>
                        </div>
                    )}
                </div>

                <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', cursor: 'pointer' }}>
                        <input type="checkbox" checked={useExisting} onChange={() => setUseExisting(!useExisting)} />
                        Додати до існуючої групи
                    </label>

                    {useExisting ? (
                        <select className="input-field" value={groupId} onChange={e => setGroupId(e.target.value)}>
                            <option value="">Оберіть групу...</option>
                            {groups.map((g: any) => <option key={g.id} value={g.id}>{g.name}</option>)}
                        </select>
                    ) : (
                        <input className="input-field" placeholder="Назва нової групи" value={newGroupName} onChange={e => setNewGroupName(e.target.value)} />
                    )}

                    <button className="btn-primary" onClick={handleImport} disabled={!file || loading} style={{ alignSelf: 'flex-start' }}>
                        {loading ? '⏳ Імпортую...' : '🚀 Почати імпорт'}
                    </button>
                </div>
            </div>

            {result && (
                <div className={`glass-card animate-slide-up`} style={{ padding: '20px' }}>
                    {result.error ? (
                        <div style={{ color: 'var(--fw-danger)' }}>❌ {result.error}</div>
                    ) : (
                        <div>
                            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px', color: 'var(--fw-success)' }}>✅ Імпорт завершено!</h3>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px' }}>
                                <div className="stat-card">
                                    <span className="stat-value">{result.stats?.messages || 0}</span>
                                    <span className="stat-label">Повідомлень</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value">{result.stats?.photos || 0}</span>
                                    <span className="stat-label">Фото</span>
                                </div>
                                <div className="stat-card">
                                    <span className="stat-value">{result.stats?.faces_queued || 0}</span>
                                    <span className="stat-label">Відправлено на розпізнавання</span>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
