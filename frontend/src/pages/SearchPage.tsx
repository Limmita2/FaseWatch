
import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { searchApi } from '@/services/api';

export default function SearchPage() {
    const [tab, setTab] = useState<'photo' | 'text'>('photo');
    const [textQuery, setTextQuery] = useState('');
    const [textResults, setTextResults] = useState<any[]>([]);
    const [photoResults, setPhotoResults] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [previewUrl, setPreviewUrl] = useState<string | null>(null);
    const [threshold, setThreshold] = useState(50);
    const [searchError, setSearchError] = useState<string | null>(null);
    const [statusMsg, setStatusMsg] = useState<string | null>(null);
    const [expandedMatch, setExpandedMatch] = useState<any>(null);
    const [selectedFaceIndex, setSelectedFaceIndex] = useState<number | null>(null);
    const [imgDims, setImgDims] = useState<{ w: number, h: number, natW: number, natH: number } | null>(null);
    const [uploadedFile, setUploadedFile] = useState<File | null>(null);

    const onDrop = useCallback(async (files: File[]) => {
        if (!files.length) return;
        setLoading(true);
        setSearchError(null);
        setPhotoResults(null);
        setSelectedFaceIndex(null);
        setImgDims(null);
        setUploadedFile(files[0]);
        setStatusMsg('🔄 Завантаження фото та пошук облич...');
        setPreviewUrl(URL.createObjectURL(files[0]));
        try {
            const { data } = await searchApi.byFace(files[0], 20, threshold);
            if (data.error) {
                setSearchError(data.error);
            } else {
                setPhotoResults(data);
                if (data.results?.length === 1) {
                    setSelectedFaceIndex(0);
                }
            }
        } catch (e: any) {
            setSearchError(e?.response?.data?.detail || e?.message || 'Помилка при пошуку');
            setPhotoResults(null);
        }
        setStatusMsg(null);
        setLoading(false);
    }, [threshold]);

    const handleFaceSelect = async (i: number) => {
        if (!uploadedFile) return;
        setLoading(true);
        setSearchError(null);
        setSelectedFaceIndex(i);
        setStatusMsg(`🔄 Пошук збігів для обличчя #${i + 1}...`);
        try {
            const { data } = await searchApi.byFace(uploadedFile, 20, threshold, i);
            if (data.error) {
                setSearchError(data.error);
            } else {
                setPhotoResults(data);
            }
        } catch (e: any) {
            setSearchError(e?.response?.data?.detail || e?.message || 'Помилка при пошуку');
        }
        setStatusMsg(null);
        setLoading(false);
    };

    const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: { 'image/*': [] }, maxFiles: 1 });

    const handleTextSearch = async () => {
        if (!textQuery.trim()) return;
        setLoading(true);
        try {
            const { data } = await searchApi.byText(textQuery);
            setTextResults(data.results || []);
        } catch { setTextResults([]); }
        setLoading(false);
    };

    return (
        <div className="animate-fade-in">
            <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '24px' }}>🔍 Пошук</h1>

            <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
                <button className={tab === 'photo' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab('photo')}>📷 За фото</button>
                <button className={tab === 'text' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab('text')}>📝 За текстом</button>
            </div>

            {tab === 'photo' && (
                <div>
                    <div {...getRootProps()} className={`dropzone ${isDragActive ? 'active' : ''}`} style={{ marginBottom: '20px' }}>
                        <input {...getInputProps()} />
                        <p style={{ fontSize: '16px', marginBottom: '8px' }}>📸 Перетягніть фото сюди або натисніть для вибору</p>
                        <p style={{ fontSize: '13px' }}>Система знайде схожі обличчя у базі (top-20)</p>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px', padding: '12px', background: 'var(--fw-card-bg)', borderRadius: 'var(--fw-radius)' }}>
                        <span style={{ fontSize: '14px', whiteSpace: 'nowrap' }}>Порог схожості:</span>
                        <input type="range" min={0} max={100} value={threshold} onChange={e => setThreshold(Number(e.target.value))} style={{ flex: 1 }} />
                        <span style={{ fontSize: '14px', fontWeight: 600, minWidth: '40px' }}>{threshold}%</span>
                    </div>

                    {previewUrl && (
                        <div style={{ marginBottom: '20px' }}>
                            {/* Main Photo (always visible) */}
                            <div style={{ display: 'inline-block', position: 'relative' }}>
                                <img
                                    src={previewUrl}
                                    alt="preview"
                                    style={{ maxWidth: 400, maxHeight: 400, borderRadius: 'var(--fw-radius)', display: 'block' }}
                                    onLoad={(e) => {
                                        const img = e.currentTarget;
                                        setImgDims({ w: img.width, h: img.height, natW: img.naturalWidth, natH: img.naturalHeight });
                                    }}
                                />
                            </div>

                            {/* Selectable Face Portraits */}
                            {photoResults && photoResults.results?.length > 1 && selectedFaceIndex === null && imgDims && (
                                <div style={{ marginTop: '24px' }}>
                                    <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>📸 Виявлено декілька облич</h3>
                                    <p style={{ color: 'var(--fw-text-dim)', marginBottom: '16px' }}>Оберіть людину, для якої виконати пошук:</p>

                                    <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                                        {photoResults.results.map((r: any, i: number) => {
                                            if (!r.bbox) return null;
                                            const [x1, y1, x2, y2] = r.bbox;

                                            // The face crop dimensions in the original image coordinates
                                            const faceWidth = x2 - x1;
                                            const faceHeight = y2 - y1;

                                            // Ensure the container is square and a reasonable size (e.g. 100x100)
                                            const containerSize = 100;

                                            // We need to scale the original image so the face fills the container
                                            const scale = containerSize / Math.max(faceWidth, faceHeight);
                                            const scaledImgWidth = imgDims.natW * scale;
                                            const scaledImgHeight = imgDims.natH * scale;

                                            // Calculate background position to center the face
                                            const bgPosX = -(x1 * scale) + (containerSize - (faceWidth * scale)) / 2;
                                            const bgPosY = -(y1 * scale) + (containerSize - (faceHeight * scale)) / 2;

                                            return (
                                                <div
                                                    key={i}
                                                    onClick={() => handleFaceSelect(i)}
                                                    className="glass-card"
                                                    style={{
                                                        width: `${containerSize}px`,
                                                        height: `${containerSize}px`,
                                                        borderRadius: '8px',
                                                        overflow: 'hidden',
                                                        cursor: 'pointer',
                                                        border: '2px solid transparent',
                                                        backgroundImage: `url(${previewUrl})`,
                                                        backgroundSize: `${scaledImgWidth}px ${scaledImgHeight}px`,
                                                        backgroundPosition: `${bgPosX}px ${bgPosY}px`,
                                                        backgroundRepeat: 'no-repeat',
                                                    }}
                                                    onMouseEnter={(e) => e.currentTarget.style.border = '2px solid var(--fw-success, #22c55e)'}
                                                    onMouseLeave={(e) => e.currentTarget.style.border = '2px solid transparent'}
                                                    title={`Обличчя #${i + 1}`}
                                                >
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {loading && (
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '40px', gap: '16px' }}>
                            <div className="spinner" />
                            {statusMsg && <p style={{ color: 'var(--fw-text-muted)', fontSize: '14px' }}>{statusMsg}</p>}
                        </div>
                    )}

                    {searchError && !loading && (
                        <div className="glass-card" style={{ padding: '20px', borderLeft: '4px solid var(--fw-danger, #ef4444)', marginBottom: '20px' }}>
                            <p style={{ color: 'var(--fw-danger, #ef4444)', fontWeight: 600, marginBottom: '4px' }}>❌ Помилка</p>
                            <p style={{ fontSize: '14px' }}>{searchError}</p>
                        </div>
                    )}

                    {photoResults && !loading && (
                        <div>
                            <p style={{ color: 'var(--fw-text-muted)', marginBottom: '16px' }}>
                                {photoResults.faces_detected > 0
                                    ? `✅ Знайдено облич на фото: ${photoResults.faces_detected}`
                                    : '⚠️ На фото не знайдено жодного обличчя. Спробуйте інше фото.'}
                            </p>

                            {photoResults.results?.length > 1 && selectedFaceIndex === null && (
                                <div className="glass-card" style={{ padding: '24px', textAlign: 'center' }}>
                                    <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>📸 Виявлено декілька облич</h3>
                                    <p style={{ color: 'var(--fw-text-dim)' }}>Будь ласка, натисніть на одне з облич на фото вище, щоб переглянути результати пошуку для нього.</p>
                                </div>
                            )}

                            {photoResults.results?.map((face: any, i: number) => {
                                if (selectedFaceIndex !== null && selectedFaceIndex !== i) return null;

                                return (
                                    <div key={i} style={{ marginBottom: '24px' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                                            <h3 style={{ fontSize: '18px', fontWeight: 600 }}>Результати для обличчя #{i + 1}</h3>
                                            {photoResults.results.length > 1 && (
                                                <button className="btn-secondary" style={{ padding: '6px 14px', fontSize: '13px' }} onClick={() => setSelectedFaceIndex(null)}>
                                                    ← Назад до вибору
                                                </button>
                                            )}
                                        </div>
                                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '24px' }}>
                                            {face.matches?.map((match: any, j: number) => (
                                                <div
                                                    key={j}
                                                    className="glass-card"
                                                    style={{ padding: '8px', cursor: 'pointer', position: 'relative', display: 'flex', flexDirection: 'column' }}
                                                    onClick={() => setExpandedMatch(match)}
                                                >
                                                    {/* Percentage Badge Overlay */}
                                                    <div style={{
                                                        position: 'absolute', top: 12, right: 12,
                                                        background: match.similarity > 80 ? 'var(--fw-success, #22c55e)' : match.similarity > 60 ? 'var(--fw-warning, #f59e0b)' : 'var(--fw-text-muted)',
                                                        color: '#fff', padding: '2px 8px', borderRadius: '6px', fontWeight: 700, fontSize: '13px', zIndex: 1, boxShadow: '0 2px 4px rgba(0,0,0,0.5)'
                                                    }}>
                                                        {match.similarity}%
                                                    </div>

                                                    <div style={{ width: '100%', aspectRatio: '1/1', background: '#000', borderRadius: '4px', overflow: 'hidden', marginBottom: '8px' }}>
                                                        <img
                                                            src={`/files/${(match.crop_path || match.photo_path || '').replace(/^\/mnt\/qnap_photos\//, '')}`}
                                                            alt="matched face"
                                                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                                            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                                                        />
                                                    </div>

                                                    <div style={{ fontWeight: 600, fontSize: '13px', textAlign: 'center', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: 'var(--fw-text)' }}>
                                                        {match.person?.display_name || `Персона ${match.person?.id?.slice(0, 8) || '—'}`}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                        {(!face.matches || face.matches.length === 0) && (
                                            <div className="glass-card" style={{ padding: '24px', textAlign: 'center', marginTop: '12px' }}>
                                                <p style={{ color: 'var(--fw-text-dim)', fontSize: '16px', marginBottom: '8px' }}>🔍 Збігів не знайдено</p>
                                                <p style={{ color: 'var(--fw-text-dim)', fontSize: '14px' }}>Це обличчя не знайдено в базі. Спробуйте знизити порог схожості.</p>
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            {tab === 'text' && (
                <div>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
                        <input className="input-field" placeholder="Введіть текст для пошуку..." value={textQuery} onChange={e => setTextQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleTextSearch()} />
                        <button className="btn-primary" onClick={handleTextSearch}>Шукати</button>
                    </div>

                    {loading && <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}><div className="spinner" /></div>}

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        {textResults.map((r: any) => (
                            <div
                                key={r.id}
                                className="glass-card"
                                style={{ padding: '14px', cursor: 'pointer', transition: 'border-color 0.2s', border: '1px solid transparent' }}
                                onClick={() => setExpandedMatch({ ...r, similarity: null })} // similarity is null for text search
                                onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--fw-primary, #3b82f6)'}
                                onMouseLeave={(e) => e.currentTarget.style.borderColor = 'transparent'}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                                    <span className="badge badge-primary">{r.group_name || '—'}</span>
                                    {r.sender_name && <span style={{ fontSize: '13px', fontWeight: 500 }}>{r.sender_name}</span>}
                                    <span style={{ fontSize: '12px', color: 'var(--fw-text-dim)', marginLeft: 'auto' }}>
                                        {r.timestamp ? new Date(r.timestamp).toLocaleString('uk-UA') : ''}
                                    </span>
                                </div>
                                <p style={{ fontSize: '14px' }}>{r.text}</p>
                            </div>
                        ))}
                        {textResults.length === 0 && !loading && textQuery && <p style={{ color: 'var(--fw-text-dim)', textAlign: 'center', padding: '24px' }}>Нічого не знайдено</p>}
                    </div>
                </div>
            )}

            {/* Modal for Expanded Match */}
            {expandedMatch && (
                <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.85)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }} onClick={() => setExpandedMatch(null)}>
                    <div className="glass-card" style={{ maxWidth: '1200px', width: '100%', maxHeight: '95vh', overflowY: 'auto', padding: '32px', position: 'relative', display: 'flex', flexDirection: 'column', gap: '24px', cursor: 'default' }} onClick={e => e.stopPropagation()}>
                        <button style={{ position: 'absolute', top: 20, right: 24, background: 'rgba(255,255,255,0.1)', border: 'none', color: '#fff', fontSize: '28px', cursor: 'pointer', borderRadius: '50%', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10 }} onClick={() => setExpandedMatch(null)}>×</button>

                        <div style={{ display: 'flex', gap: '32px', flexWrap: 'wrap' }}>
                            {/* Left side: Photo */}
                            {(expandedMatch.photo_path || expandedMatch.crop_path) && (
                                <div style={{ flex: '1 1 500px', display: 'flex', flexDirection: 'column', gap: '16px', alignItems: 'center' }}>
                                    <img
                                        src={`/files/${(expandedMatch.photo_path || expandedMatch.crop_path || '').replace(/^\/mnt\/qnap_photos\//, '')}`}
                                        alt="expanded match"
                                        style={{ width: '75%', borderRadius: 'var(--fw-radius)', border: expandedMatch.similarity !== null && expandedMatch.similarity !== undefined ? `3px solid ${expandedMatch.similarity > 80 ? 'var(--fw-success, #22c55e)' : 'var(--fw-warning, #f59e0b)'}` : '3px solid var(--fw-primary, #3b82f6)', objectFit: 'contain', maxHeight: '40vh' }}
                                    />
                                    {expandedMatch.similarity !== null && expandedMatch.similarity !== undefined && (
                                        <div style={{ textAlign: 'center', fontSize: '24px', fontWeight: 700, color: expandedMatch.similarity > 80 ? 'var(--fw-success, #22c55e)' : 'var(--fw-warning, #f59e0b)' }}>
                                            Схожість: {expandedMatch.similarity}%
                                        </div>
                                    )}
                                    {expandedMatch.person && (
                                        <div style={{ textAlign: 'center', color: 'var(--fw-text-muted)', fontSize: '18px' }}>
                                            {expandedMatch.person.display_name || `Персона ${expandedMatch.person.id?.slice(0, 8) || '—'}`}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Right side: Context */}
                            <div style={{ flex: '2 1 400px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '8px' }}>Контекст</h3>

                                {expandedMatch.context ? (
                                    <div style={{ background: 'rgba(0,0,0,0.2)', borderRadius: '8px', padding: '16px', fontSize: '15px', flex: 1 }}>
                                        <div style={{ marginBottom: '16px' }}>
                                            <span className="badge badge-primary">📂 Группа: {expandedMatch.context.group_name || '—'}</span>
                                        </div>

                                        {expandedMatch.context.before?.map((msg: any, idx: number) => (
                                            <div key={msg.id || idx} style={{ padding: '8px 0', color: 'var(--fw-text-muted)', borderLeft: '2px solid var(--fw-text-dim)', paddingLeft: '12px', marginBottom: '12px' }}>
                                                <span style={{ fontSize: '12px', opacity: 0.6 }}>{msg.timestamp?.slice(11, 16)}</span><br />
                                                {msg.sender_name && <b style={{ color: 'var(--fw-text)' }}>{msg.sender_name}: </b>}
                                                {msg.text}
                                                {msg.photo_path && (
                                                    <img src={`/files/${msg.photo_path.replace(/^\/mnt\/qnap_photos\//, '')}`} alt="context before" style={{ width: '50%', borderRadius: '8px', marginTop: '8px', display: 'block', maxHeight: '200px', objectFit: 'contain' }} />
                                                )}
                                                {!msg.text && !msg.photo_path && msg.has_photo && '📷 Фото (не завантажено)'}
                                            </div>
                                        ))}

                                        <div style={{
                                            padding: '12px 16px', marginBottom: '12px',
                                            background: 'rgba(34, 197, 94, 0.15)',
                                            borderLeft: '4px solid var(--fw-success, #22c55e)',
                                            borderRadius: '6px', fontWeight: 500,
                                        }}>
                                            <span style={{ fontSize: '12px', opacity: 0.6 }}>{expandedMatch.context.message?.timestamp?.slice(11, 16)}</span><br />
                                            ★ {expandedMatch.context.message?.sender_name && <b style={{ color: 'var(--fw-text)' }}>{expandedMatch.context.message.sender_name}: </b>}
                                            {expandedMatch.context.message?.text}
                                            {expandedMatch.context.message?.photo_path && (
                                                <img src={`/files/${expandedMatch.context.message.photo_path.replace(/^\/mnt\/qnap_photos\//, '')}`} alt="matched context" style={{ width: '50%', borderRadius: '8px', marginTop: '8px', display: 'block', maxHeight: '200px', objectFit: 'contain' }} />
                                            )}
                                        </div>

                                        {expandedMatch.context.after?.map((msg: any, idx: number) => (
                                            <div key={msg.id || idx} style={{ padding: '8px 0', color: 'var(--fw-text-muted)', borderLeft: '2px solid var(--fw-text-dim)', paddingLeft: '12px', marginBottom: '12px' }}>
                                                <span style={{ fontSize: '12px', opacity: 0.6 }}>{msg.timestamp?.slice(11, 16)}</span><br />
                                                {msg.sender_name && <b style={{ color: 'var(--fw-text)' }}>{msg.sender_name}: </b>}
                                                {msg.text}
                                                {msg.photo_path && (
                                                    <img src={`/files/${msg.photo_path.replace(/^\/mnt\/qnap_photos\//, '')}`} alt="context after" style={{ width: '50%', borderRadius: '8px', marginTop: '8px', display: 'block', maxHeight: '200px', objectFit: 'contain' }} />
                                                )}
                                                {!msg.text && !msg.photo_path && msg.has_photo && '📷 Фото (не завантажено)'}
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div style={{ color: 'var(--fw-text-dim)', padding: '20px', textAlign: 'center', background: 'rgba(0,0,0,0.1)', borderRadius: '8px' }}>
                                        Контекст бази відсутній
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
