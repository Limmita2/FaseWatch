const fs = require('fs')
const path = require('path')
const axios = require('axios')
const sharp = require('sharp')
const qrcode = require('qrcode-terminal')
const {
    default: makeWASocket,
    DisconnectReason,
    useMultiFileAuthState,
    downloadMediaMessage,
    fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys')

const SESSION_DIR = '/app/session'
const BACKEND_URL = (process.env.WHATSAPP_BACKEND_URL || 'http://facewatch_backend:8000').replace(/\/$/, '')
const BOT_API_KEY = (process.env.BOT_API_KEY || '').trim()
const INTERNAL_API_KEY = (process.env.TELETHON_API_KEY || '').trim()
const RECONNECT_DELAY_MS = 5000
const REFRESH_INTERVAL_MS = 180000
const DISCOVERY_MIN_INTERVAL_MS = 180000
const DISCOVERY_RETRY_DELAY_MS = 60000
const ON_DEMAND_HISTORY_BATCH_SIZE = 100
const ON_DEMAND_HISTORY_MAX_BATCHES = 20

let trackedGroups = new Map()
let historyProgress = new Map()
let historyAnchors = new Map()
let historyBackfillState = new Map()
let refreshTimer = null
let historyFinalizeTimer = null
let historyBackfillTimer = null
let discoveryInFlight = false
let discoveryQueued = false
let discoveryRetryTimer = null
let lastDiscoveryAt = 0

function log(level, message, meta) {
    const timestamp = new Date().toISOString()
    if (meta === undefined) {
        console[level](`${timestamp} ${message}`)
        return
    }
    console[level](`${timestamp} ${message}`, meta)
}

function getInternalHeaders() {
    return INTERNAL_API_KEY ? { 'X-Api-Key': INTERNAL_API_KEY } : {}
}

function getBotHeaders() {
    return BOT_API_KEY ? { 'X-API-Key': BOT_API_KEY } : {}
}

function unwrapMessageContent(message) {
    let current = message || {}
    while (current.ephemeralMessage || current.viewOnceMessage || current.viewOnceMessageV2 || current.documentWithCaptionMessage) {
        if (current.ephemeralMessage) {
            current = current.ephemeralMessage.message || {}
            continue
        }
        if (current.viewOnceMessage) {
            current = current.viewOnceMessage.message || {}
            continue
        }
        if (current.viewOnceMessageV2) {
            current = current.viewOnceMessageV2.message || {}
            continue
        }
        if (current.documentWithCaptionMessage) {
            current = current.documentWithCaptionMessage.message || {}
            continue
        }
    }
    return current
}

function extractText(content) {
    if (!content || typeof content !== 'object') {
        return ''
    }
    return (
        content.conversation ||
        content.extendedTextMessage?.text ||
        content.imageMessage?.caption ||
        content.videoMessage?.caption ||
        content.documentMessage?.caption ||
        ''
    )
}

function toIsoTimestamp(rawValue) {
    if (rawValue == null) {
        return new Date().toISOString()
    }
    const numeric = Number(rawValue)
    if (!Number.isFinite(numeric) || numeric <= 0) {
        return new Date().toISOString()
    }
    const milliseconds = numeric > 10_000_000_000 ? numeric : numeric * 1000
    return new Date(milliseconds).toISOString()
}

function toTimestampMs(rawValue) {
    if (!rawValue) {
        return 0
    }
    const parsed = Date.parse(rawValue)
    return Number.isFinite(parsed) ? parsed : 0
}

function updateHistoryAnchor(remoteJid, messageId, timestampValue, fromMe = false) {
    if (!remoteJid || !messageId) {
        return
    }
    const timestampMs = typeof timestampValue === 'number' ? timestampValue : toTimestampMs(timestampValue)
    if (!timestampMs) {
        return
    }

    const current = historyAnchors.get(remoteJid)
    if (!current || timestampMs < current.timestampMs) {
        historyAnchors.set(remoteJid, {
            id: messageId,
            timestampMs,
            fromMe: Boolean(fromMe),
        })
    }
}

function primeHistoryAnchorsFromTrackedGroups() {
    for (const [externalId, group] of trackedGroups.entries()) {
        if (group.oldest_message_id && group.oldest_message_timestamp) {
            updateHistoryAnchor(
                externalId,
                group.oldest_message_id,
                group.oldest_message_timestamp,
                false
            )
        }
    }
}

async function sendTextToBackend(payload) {
    return axios.post(`${BACKEND_URL}/api/bot/message`, payload, {
        headers: getBotHeaders(),
        timeout: 60000,
    })
}

async function sendPhotoToBackend(payload, imageBuffer) {
    const form = new FormData()
    for (const [key, value] of Object.entries(payload)) {
        form.append(key, value ?? '')
    }
    form.append('photo', new Blob([imageBuffer], { type: 'image/jpeg' }), 'whatsapp.jpg')

    return axios.post(`${BACKEND_URL}/api/bot/message`, form, {
        headers: getBotHeaders(),
        timeout: 120000,
        maxBodyLength: Infinity,
    })
}

async function refreshTrackedGroups() {
    try {
        const response = await axios.get(`${BACKEND_URL}/api/platforms/whatsapp/groups/internal`, {
            headers: getInternalHeaders(),
            timeout: 30000,
        })
        trackedGroups = new Map((response.data || []).map((group) => [group.external_id, group]))
        primeHistoryAnchorsFromTrackedGroups()
    } catch (error) {
        log('error', 'Не удалось получить список активных WhatsApp-групп', error?.response?.data || error.message)
    }
}

async function syncDiscoveredGroups(sock, status = 'active', lastError = null) {
    discoveryInFlight = true
    try {
        const groups = await sock.groupFetchAllParticipating()
        const payload = {
            account_identifier: sock.user?.id || null,
            status,
            last_error: lastError,
            meta: {
                me: sock.user || null,
            },
            groups: Object.values(groups || {}).map((group) => ({
                external_id: group.id,
                name: group.subject || group.id,
                metadata: {
                    owner: group.owner,
                    announce: group.announce,
                    size: Array.isArray(group.participants) ? group.participants.length : undefined,
                },
            })),
        }
        await axios.post(`${BACKEND_URL}/api/platforms/whatsapp/sync/internal`, payload, {
            headers: getInternalHeaders(),
            timeout: 60000,
        })
        await refreshTrackedGroups()
        lastDiscoveryAt = Date.now()
        log('info', `WhatsApp discovery sync завершен, групп: ${payload.groups.length}`)
    } catch (error) {
        const details = error?.response?.data || error.message
        log('error', 'Не удалось синхронизировать WhatsApp-группы с backend', details)
        if (String(details).includes('rate-overlimit')) {
            if (discoveryRetryTimer) {
                clearTimeout(discoveryRetryTimer)
            }
            discoveryRetryTimer = setTimeout(() => {
                discoveryRetryTimer = null
                scheduleDiscoverySync(sock, status, lastError, true)
            }, DISCOVERY_RETRY_DELAY_MS)
        }
    } finally {
        discoveryInFlight = false
        if (discoveryQueued) {
            discoveryQueued = false
            scheduleDiscoverySync(sock, status, lastError, false)
        }
    }
}

function scheduleDiscoverySync(sock, status = 'active', lastError = null, force = false) {
    if (discoveryInFlight) {
        discoveryQueued = true
        return
    }

    const now = Date.now()
    if (!force && now - lastDiscoveryAt < DISCOVERY_MIN_INTERVAL_MS) {
        return
    }

    syncDiscoveredGroups(sock, status, lastError).catch((error) => {
        log('error', 'Ошибка планировщика discovery sync WhatsApp', error)
    })
}

async function updateGroupProgress(groupDbId, progress, lastCursor, done = false) {
    try {
        await axios.patch(`${BACKEND_URL}/api/platforms/whatsapp/groups/${groupDbId}/progress/internal`, {
            history_load_progress: progress,
            last_cursor: lastCursor,
            history_loaded: done,
        }, {
            headers: getInternalHeaders(),
            timeout: 30000,
        })
    } catch (error) {
        log('error', `Не удалось обновить прогресс history для WhatsApp group_id=${groupDbId}`, error?.response?.data || error.message)
    }
}

function scheduleHistoryFinalize() {
    if (historyFinalizeTimer) {
        clearTimeout(historyFinalizeTimer)
    }
    historyFinalizeTimer = setTimeout(async () => {
        for (const [externalId, group] of trackedGroups.entries()) {
            const current = historyProgress.get(externalId) || { count: group.history_load_progress || 0, lastCursor: group.last_cursor || null }
            await updateGroupProgress(group.group_id, current.count, current.lastCursor, true)
        }
        await refreshTrackedGroups()
        log('info', 'WhatsApp history sync помечен как завершенный для активных групп')
    }, 15000)
}

async function requestOlderHistoryForGroup(sock, remoteJid, force = false) {
    const trackedGroup = trackedGroups.get(remoteJid)
    const anchor = historyAnchors.get(remoteJid)
    if (!trackedGroup || !trackedGroup.is_active || !anchor?.id || !anchor.timestampMs) {
        return false
    }

    const state = historyBackfillState.get(remoteJid) || { batchesRequested: 0, inFlight: false, done: false }
    if (state.inFlight || state.done) {
        return false
    }
    if (!force && state.batchesRequested >= ON_DEMAND_HISTORY_MAX_BATCHES) {
        state.done = true
        historyBackfillState.set(remoteJid, state)
        return false
    }

    state.inFlight = true
    historyBackfillState.set(remoteJid, state)
    try {
        await sock.fetchMessageHistory(
            ON_DEMAND_HISTORY_BATCH_SIZE,
            {
                remoteJid,
                id: anchor.id,
                fromMe: anchor.fromMe,
            },
            anchor.timestampMs
        )
        state.batchesRequested += 1
        log('info', `Запрошена догрузка истории WhatsApp: group=${trackedGroup.name} batch=${state.batchesRequested}`)
        return true
    } catch (error) {
        log('error', `Не удалось запросить догрузку истории WhatsApp для group=${trackedGroup.name}`, error?.message || error)
        return false
    } finally {
        state.inFlight = false
        historyBackfillState.set(remoteJid, state)
    }
}

function scheduleHistoryBackfill(sock, force = false, delayMs = 2500) {
    if (historyBackfillTimer) {
        clearTimeout(historyBackfillTimer)
    }
    historyBackfillTimer = setTimeout(async () => {
        await refreshTrackedGroups()
        for (const remoteJid of trackedGroups.keys()) {
            await requestOlderHistoryForGroup(sock, remoteJid, force)
        }
    }, delayMs)
}

async function processMediaMessage(sock, msg, payload, content, sourceType) {
    const imageMessage = content.imageMessage
    const videoMessage = content.videoMessage
    if (videoMessage) {
        log('info', `Видео WhatsApp пропущено: group=${payload.group_external_id} sender=${payload.sender_name}`)
        return false
    }
    if (!imageMessage) {
        return false
    }

    const mimeType = String(imageMessage.mimetype || '').toLowerCase()
    if (!mimeType.startsWith('image/') || mimeType.includes('gif')) {
        log('info', `Неподдерживаемое изображение WhatsApp пропущено: ${mimeType}`)
        return false
    }

    const buffer = await downloadMediaMessage(
        msg,
        'buffer',
        {},
        { reuploadRequest: sock.updateMediaMessage }
    )
    const jpegBuffer = await sharp(buffer).jpeg({ quality: 92 }).toBuffer()
    const response = await sendPhotoToBackend({ ...payload, source_type: sourceType }, jpegBuffer)
    log('info', `WhatsApp ${sourceType === 'history' ? 'history photo' : 'photo'} отправлено в backend`, response.data)
    return true
}

async function processAnyMessage(sock, msg, sourceType) {
    if (!msg?.message || !msg?.key) {
        return
    }

    const remoteJid = msg.key.remoteJid || ''
    if (!remoteJid.endsWith('@g.us')) {
        return
    }

    if (sourceType === 'bot' && msg.key.fromMe) {
        log('info', 'Пропущено собственное исходящее сообщение WhatsApp')
        return
    }

    const trackedGroup = trackedGroups.get(remoteJid)
    if (!trackedGroup || !trackedGroup.is_active) {
        return
    }

    const content = unwrapMessageContent(msg.message)
    const text = extractText(content)
    const senderId = msg.key.participant || ''
    const senderName = msg.pushName || senderId || 'Unknown'
    const payload = {
        group_external_id: remoteJid,
        group_name: trackedGroup.name || remoteJid,
        message_id: msg.key.id || '',
        sender_external_id: senderId,
        sender_name: senderName,
        text,
        timestamp: toIsoTimestamp(msg.messageTimestamp),
        source_platform: 'whatsapp',
        source_type: sourceType,
    }

    if (!payload.message_id) {
        return
    }

    updateHistoryAnchor(remoteJid, payload.message_id, payload.timestamp, msg.key.fromMe)

    const mediaProcessed = await processMediaMessage(sock, msg, payload, content, sourceType)
    if (!mediaProcessed && text) {
        const response = await sendTextToBackend(payload)
        log('info', `WhatsApp ${sourceType === 'history' ? 'history text' : 'text'} отправлено в backend`, response.data)
    }

    if (sourceType === 'history') {
        const current = historyProgress.get(remoteJid) || { count: 0, lastCursor: null }
        current.count += 1
        current.lastCursor = payload.message_id
        historyProgress.set(remoteJid, current)
        if (current.count % 50 === 0) {
            await updateGroupProgress(trackedGroup.group_id, current.count, current.lastCursor, false)
        }
    }
}

async function startSocket() {
    fs.mkdirSync(SESSION_DIR, { recursive: true })
    const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR)
    const { version } = await fetchLatestBaileysVersion()

    const sock = makeWASocket({
        version,
        auth: state,
        markOnlineOnConnect: false,
        generateHighQualityLinkPreview: false,
        printQRInTerminal: false,
        syncFullHistory: true,
        shouldSyncHistoryMessage: () => true,
    })

    sock.ev.on('creds.update', saveCreds)

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update
        if (qr) {
            log('info', 'Сканируйте QR-код WhatsApp в терминале:')
            qrcode.generate(qr, { small: true })
        }

        if (connection === 'open') {
            log('info', 'WhatsApp подключен')
            await syncDiscoveredGroups(sock, 'active', null)
            await refreshTrackedGroups()
            if (refreshTimer) {
                clearInterval(refreshTimer)
            }
            refreshTimer = setInterval(async () => {
                scheduleDiscoverySync(sock, 'active', null)
                scheduleHistoryBackfill(sock, false, 2000)
            }, REFRESH_INTERVAL_MS)
            scheduleHistoryFinalize()
            scheduleHistoryBackfill(sock, false, 8000)
        }

        if (connection === 'close') {
            if (refreshTimer) {
                clearInterval(refreshTimer)
                refreshTimer = null
            }
            const statusCode = lastDisconnect?.error?.output?.statusCode
            if (statusCode === DisconnectReason.loggedOut) {
                await syncDiscoveredGroups(sock, 'logged_out', 'session_lost')
                log('error', 'Сессия WhatsApp потеряна, процесс будет завершен для показа нового QR')
                process.exit(1)
            }
            await syncDiscoveredGroups(sock, 'reconnecting', String(statusCode || 'connection_closed'))
            log('warn', `Соединение WhatsApp закрыто (code=${statusCode ?? 'unknown'}), переподключение через 5 секунд`)
            setTimeout(() => {
                startSocket().catch((error) => {
                    log('error', 'Ошибка повторного подключения WhatsApp', error)
                    process.exit(1)
                })
            }, RECONNECT_DELAY_MS)
        }
    })

    sock.ev.on('messaging-history.set', async ({ messages, isLatest, syncType, progress }) => {
        if (!Array.isArray(messages)) {
            return
        }
        await refreshTrackedGroups()
        log('info', `Получен history batch WhatsApp: messages=${messages.length} syncType=${syncType ?? 'unknown'} progress=${progress ?? 'n/a'}`)
        for (const msg of messages) {
            try {
                await processAnyMessage(sock, msg, 'history')
            } catch (error) {
                log('error', 'Ошибка обработки history sync WhatsApp', error)
            }
        }
        if (isLatest) {
            scheduleHistoryFinalize()
        }
        scheduleHistoryBackfill(sock, false, 4000)
    })

    sock.ev.on('groups.update', async () => {
        scheduleDiscoverySync(sock, 'active', null)
    })
    sock.ev.on('groups.upsert', async () => {
        scheduleDiscoverySync(sock, 'active', null)
    })

    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        if (type !== 'notify' || !Array.isArray(messages)) {
            return
        }
        await refreshTrackedGroups()
        for (const msg of messages) {
            try {
                await processAnyMessage(sock, msg, 'bot')
            } catch (error) {
                log('error', 'Ошибка обработки сообщения WhatsApp', error)
            }
        }
    })
}

startSocket().catch((error) => {
    log('error', 'Фатальная ошибка запуска WhatsApp бота', error)
    process.exit(1)
})
