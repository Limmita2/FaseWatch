from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.core.config import settings
import uuid

COLLECTION_NAME = "faces"
VECTOR_SIZE = 512

# Поріг схожості для об'єднання лиць в одну особу (70%)
PERSON_THRESHOLD = float(0.60)


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


def ensure_collection_exists():
    """Створює колекцію faces у Qdrant, якщо її немає."""
    client = get_qdrant_client()
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        # Payload-індекси для швидкої фільтрації при пошуку
        for field in ("message_id", "face_id", "group_id", "person_id"):
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema="keyword",
            )
    return client


def upsert_face_vector(
    client: QdrantClient,
    face_id: str,
    vector: list[float],
    payload: dict,
):
    """Зберігає вектор лиця у Qdrant."""
    point_id = str(uuid.uuid4())
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )
    return point_id


def search_similar_faces(
    client: QdrantClient,
    vector: list[float],
    top_k: int = 5,
    score_threshold: float = 0.0,
    group_ids: list[str] = None,
):
    """Шукає схожі лиця у Qdrant."""
    from qdrant_client.models import Filter, FieldCondition, MatchAny

    query_filter = None
    if group_ids is not None:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="group_id",
                    match=MatchAny(any=group_ids)
                )
            ]
        )

    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=top_k,
        score_threshold=score_threshold if score_threshold > 0 else None,
        query_filter=query_filter,
    )
    return result.points


def find_person_for_vector(
    client: QdrantClient,
    vector: list[float],
    threshold: float = PERSON_THRESHOLD,
) -> str | None:
    """
    Шукає існуючу особу (person_id) для нового вектора лиця.
    Повертає person_id якщо знайдено схоже лице, або None якщо нова особа.
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    # Шукаємо лише серед лиць, що вже мають person_id
    query_filter = Filter(
        must_not=[
            FieldCondition(key="person_id", match=MatchValue(value=""))
        ]
    )

    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=1,
        score_threshold=threshold,
        with_payload=True,
    )

    if result.points and result.points[0].payload.get("person_id"):
        return result.points[0].payload["person_id"]
    return None


def update_point_person_id(client: QdrantClient, point_id: str, person_id: str):
    """Оновлює person_id у payload конкретної точки Qdrant."""
    from qdrant_client.models import SetPayload
    client.set_payload(
        collection_name=COLLECTION_NAME,
        payload={"person_id": person_id},
        points=[point_id],
    )
