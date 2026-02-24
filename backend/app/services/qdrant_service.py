from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.core.config import settings
import uuid

COLLECTION_NAME = "faces"
VECTOR_SIZE = 512


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


def ensure_collection_exists():
    """Создаёт коллекцию faces в Qdrant, если её нет."""
    client = get_qdrant_client()
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    return client


def upsert_face_vector(
    client: QdrantClient,
    face_id: str,
    vector: list[float],
    payload: dict,
):
    """Сохраняет вектор лица в Qdrant."""
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
):
    """Ищет похожие лица в Qdrant (qdrant-client >= 1.17.0)."""
    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=top_k,
        score_threshold=score_threshold if score_threshold > 0 else None,
    )
    return result.points

