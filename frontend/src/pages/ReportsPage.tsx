import { useEffect, useState } from 'react';

import { aiApi } from '@/services/api';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

interface ReportItem {
    id: string;
    title: string;
    report_type: string;
    context_id?: string | null;
    created_at?: string | null;
}

export default function ReportsPage() {
    const [reports, setReports] = useState<ReportItem[]>([]);
    const [selected, setSelected] = useState<ReportItem | null>(null);
    const [content, setContent] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);

    const token = localStorage.getItem('token') || '';

    const loadReports = async () => {
        setLoading(true);
        try {
            const res = await aiApi.reports();
            setReports(res.data);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося завантажити звіти');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadReports();
    }, []);

    const handleView = async (report: ReportItem) => {
        setSelected(report);
        try {
            const res = await aiApi.report(report.id);
            setContent(res.data.content || '');
        } catch {
            setContent('');
        }
    };

    const handleDelete = async (reportId: string) => {
        if (!confirm('Видалити звіт?')) return;
        try {
            await aiApi.deleteReport(reportId);
            if (selected?.id === reportId) {
                setSelected(null);
                setContent('');
            }
            await loadReports();
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Не вдалося видалити звіт');
        }
    };

    const handleDownloadPdf = async (reportId: string) => {
        try {
            const response = await fetch(`${API_BASE}/api/ai/reports/${reportId}/pdf`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!response.ok) {
                throw new Error('PDF export failed');
            }
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `report-${reportId}.pdf`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        } catch (err: any) {
            setError(err.message || 'Не вдалося завантажити PDF');
        }
    };

    return (
        <div className="animate-fade-in">
            <h1 style={{ fontSize: '24px', fontWeight: 800, marginBottom: '24px', color: 'var(--fw-primary)', textTransform: 'uppercase', letterSpacing: '2px', textShadow: 'var(--fw-glow-primary)' }}>
                [ ЗБЕРЕЖЕНІ ЗВІТИ AI ]
            </h1>

            {error && <div style={{ marginBottom: '12px', color: '#ef4444' }}>{error}</div>}

            <div className="glass-card" style={{ overflow: 'hidden' }}>
                {loading ? (
                    <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}><div className="spinner" /></div>
                ) : (
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr>
                                <th style={{ padding: '14px 18px', textAlign: 'left' }}>Назва</th>
                                <th style={{ padding: '14px 18px', textAlign: 'left' }}>Тип</th>
                                <th style={{ padding: '14px 18px', textAlign: 'left' }}>Контекст</th>
                                <th style={{ padding: '14px 18px', textAlign: 'left' }}>Дата</th>
                                <th style={{ padding: '14px 18px', textAlign: 'right' }}>Дії</th>
                            </tr>
                        </thead>
                        <tbody>
                            {reports.map(report => (
                                <tr key={report.id} style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                                    <td style={{ padding: '14px 18px' }}>{report.title}</td>
                                    <td style={{ padding: '14px 18px' }}><span className="badge badge-primary">{report.report_type}</span></td>
                                    <td style={{ padding: '14px 18px', fontFamily: 'monospace' }}>{report.context_id || '—'}</td>
                                    <td style={{ padding: '14px 18px' }}>{report.created_at ? new Date(report.created_at).toLocaleString('uk-UA') : '—'}</td>
                                    <td style={{ padding: '14px 18px', textAlign: 'right' }}>
                                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', flexWrap: 'wrap' }}>
                                            <button className="btn-secondary" onClick={() => handleView(report)}>Переглянути</button>
                                            <button className="btn-primary" onClick={() => handleDownloadPdf(report.id)}>PDF</button>
                                            <button className="btn-danger" onClick={() => handleDelete(report.id)}>Видалити</button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                            {reports.length === 0 && (
                                <tr>
                                    <td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: 'var(--fw-text-dim)' }}>Звітів поки немає</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                )}
            </div>

            {selected && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div className="glass-card" style={{ width: 'min(900px, 92vw)', maxHeight: '85vh', overflow: 'auto', padding: '24px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                            <div>
                                <h2 style={{ margin: 0 }}>{selected.title}</h2>
                                <div style={{ color: 'var(--fw-text-muted)', marginTop: '6px' }}>{selected.report_type} · {selected.created_at ? new Date(selected.created_at).toLocaleString('uk-UA') : '—'}</div>
                            </div>
                            <button className="btn-secondary" onClick={() => setSelected(null)}>Закрити</button>
                        </div>
                        <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: `'Courier New', Courier, monospace`, lineHeight: '1.5' }}>{content || 'Вміст недоступний'}</pre>
                    </div>
                </div>
            )}
        </div>
    );
}
