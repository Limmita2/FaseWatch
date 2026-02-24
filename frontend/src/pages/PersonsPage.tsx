import { useEffect, useState } from 'react';
import { personsApi } from '@/services/api';

export default function PersonsPage() {
    const [persons, setPersons] = useState<any[]>([]);
    const [selected, setSelected] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        personsApi.list().then(r => { setPersons(r.data); setLoading(false); }).catch(() => setLoading(false));
    }, []);

    const openPerson = async (id: string) => {
        const { data } = await personsApi.get(id);
        setSelected(data);
    };

    if (loading) return <div style={{ display: 'flex', justifyContent: 'center', padding: '80px' }}><div className="spinner" /></div>;

    return (
        <div className="animate-fade-in">
            <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '24px' }}>👤 Персони</h1>

            {selected ? (
                <div>
                    <button className="btn-secondary" onClick={() => setSelected(null)} style={{ marginBottom: '16px' }}>← Назад до списку</button>
                    <div className="glass-card" style={{ padding: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '20px' }}>
                            <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'linear-gradient(135deg, var(--fw-primary), var(--fw-accent))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '28px' }}>
                                👤
                            </div>
                            <div>
                                <h2 style={{ fontSize: '20px', fontWeight: 700 }}>{selected.display_name || `ID: ${selected.id.slice(0, 8)}`}</h2>
                                <span className={`badge ${selected.confirmed ? 'badge-success' : 'badge-warning'}`}>
                                    {selected.confirmed ? 'Підтверджено' : 'Не підтверджено'}
                                </span>
                            </div>
                        </div>
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Обличчя ({selected.faces?.length || 0})</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '12px' }}>
                            {selected.faces?.map((face: any) => (
                                <div key={face.id} className="glass-card" style={{ padding: '8px', textAlign: 'center' }}>
                                    {face.crop_path ? (
                                        <img
                                            src={`/files/${face.crop_path.replace(/^\/mnt\/qnap_photos\//, '')}`}
                                            alt="face"
                                            style={{ width: '100%', borderRadius: 'var(--fw-radius-sm)' }}
                                            onError={(e) => { (e.currentTarget as HTMLImageElement).src = ''; e.currentTarget.style.display = 'none'; }}
                                        />
                                    ) : (
                                        <div style={{ height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fw-text-dim)' }}>🧑</div>
                                    )}
                                    <p style={{ fontSize: '11px', color: 'var(--fw-text-dim)', marginTop: '4px' }}>{face.confidence ? `${(face.confidence * 100).toFixed(0)}%` : '—'}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            ) : (
                <div className="glass-card table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Ім'я</th>
                                <th>Статус</th>
                                <th>Облич</th>
                                <th>Дії</th>
                            </tr>
                        </thead>
                        <tbody>
                            {persons.map((p: any) => (
                                <tr key={p.id}>
                                    <td style={{ fontWeight: 500 }}>{p.display_name || <span style={{ color: 'var(--fw-text-dim)' }}>ID: {p.id.slice(0, 8)}</span>}</td>
                                    <td><span className={`badge ${p.confirmed ? 'badge-success' : 'badge-warning'}`}>{p.confirmed ? '✓' : '?'}</span></td>
                                    <td>{p.face_count}</td>
                                    <td><button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => openPerson(p.id)}>Відкрити</button></td>
                                </tr>
                            ))}
                            {persons.length === 0 && <tr><td colSpan={4} style={{ textAlign: 'center', color: 'var(--fw-text-dim)', padding: '24px' }}>Персон поки немає</td></tr>}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
