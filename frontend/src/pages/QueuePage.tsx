import { useEffect, useState } from 'react';
import { queueApi } from '@/services/api';

export default function QueuePage() {
    const [items, setItems] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    const loadQueue = () => {
        setLoading(true);
        queueApi.list().then(r => { setItems(r.data); setLoading(false); }).catch(() => setLoading(false));
    };

    useEffect(() => { loadQueue(); }, []);

    const handleConfirm = async (id: string) => {
        await queueApi.confirm(id);
        loadQueue();
    };

    const handleReject = async (id: string) => {
        await queueApi.reject(id);
        loadQueue();
    };

    if (loading) return <div style={{ display: 'flex', justifyContent: 'center', padding: '80px' }}><div className="spinner" /></div>;

    return (
        <div className="animate-fade-in">
            <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '24px' }}>
                ✅ Черга ідентифікацій
                {items.length > 0 && <span className="badge badge-warning" style={{ marginLeft: '10px' }}>{items.length}</span>}
            </h1>

            {items.length === 0 ? (
                <div className="glass-card" style={{ padding: '40px', textAlign: 'center' }}>
                    <p style={{ fontSize: '48px', marginBottom: '12px' }}>🎉</p>
                    <p style={{ color: 'var(--fw-text-muted)' }}>Черга порожня — все підтверджено!</p>
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {items.map((item: any) => (
                        <div key={item.id} className="glass-card" style={{ padding: '16px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
                                <div>
                                    <p style={{ fontSize: '14px', marginBottom: '4px' }}>
                                        <strong>Face ID:</strong> {item.face_id?.slice(0, 12)}...
                                    </p>
                                    <p style={{ fontSize: '13px', color: 'var(--fw-text-muted)' }}>
                                        Запропонована персона: {item.suggested_person_id?.slice(0, 12) || '—'}
                                    </p>
                                    <div style={{ marginTop: '6px' }}>
                                        <span className={`badge ${item.similarity > 0.85 ? 'badge-success' : 'badge-warning'}`}>
                                            Схожість: {(item.similarity * 100).toFixed(1)}%
                                        </span>
                                    </div>
                                </div>
                                <div style={{ display: 'flex', gap: '8px' }}>
                                    <button className="btn-success" onClick={() => handleConfirm(item.id)}>✓ Підтвердити</button>
                                    <button className="btn-danger" onClick={() => handleReject(item.id)}>✗ Відхилити</button>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
