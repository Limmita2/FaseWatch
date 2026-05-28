# FaceWatch Gemini Instructions

You are working in the FaceWatch repository.

## Database Work

- Treat the production database as read-only.
- Never run `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `REPLACE`, `GRANT`, `REVOKE`, `LOCK`, or other mutating SQL.
- Prefer the safe helper for operational questions:

```bash
docker exec facewatch_backend python -m app.tools.ai_db_query "посчитай сколько в группе -1003936790632 всего объектов и сколько фотографий"
```

- For raw SQL, use only validated `SELECT` or `WITH`:

```bash
docker exec facewatch_backend python -m app.tools.ai_db_query --sql "SELECT COUNT(*) AS total_records FROM messages"
```

## FaceWatch Schema Notes

- `groups`: Telegram/Signal/WhatsApp sources. Important fields: `id`, `telegram_id`, `external_id`, `source_platform`, `name`.
- `messages`: imported objects/messages. Important fields: `id`, `group_id`, `text`, `has_photo`, `photo_path`, `timestamp`, `source_platform`.
- `faces`: detected face objects. Important fields: `id`, `message_id`, `person_id`, `crop_path`, `det_score`, `created_at`.
- `persons`: clustered identities. Important fields: `id`, `face_count`, `thumbnail_face_id`, `created_at`.
- A user's "объекты" usually means records in `messages`; "фотографии" means `messages.has_photo = true`; `person_id` analytics usually require `faces.person_id`.

## Answering Rules

- Answer in Russian unless the user asks otherwise.
- Give exact counts and the group name when available.
- If a question mentions a Telegram group id like `-1003936790632`, match it against `groups.telegram_id` and `groups.external_id`.
- If the user asks for a photo by `person_id`, use the app search endpoint or query `faces` joined to `messages` and report `crop_path` and `photo_path`.
- Do not invent data. If the helper cannot answer, say what extra input is needed.
