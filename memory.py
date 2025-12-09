import os
from datetime import date
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance


# Load Qdrant credentials
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")

# OpenAI client for embeddings
OPENAI_KEY = os.environ.get("OPENAI_KEY")
client = OpenAI(api_key=OPENAI_KEY)


def init_qdrant():
    """Initializes Qdrant client if credentials exist."""
    if not QDRANT_URL or not QDRANT_API_KEY:
        print("Qdrant not configured. Skipping article memory storage.")
        return None

    return QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
    )


def ensure_collection(qdrant):
    """Creates the article memory collection if not present."""
    if qdrant is None:
        return

    try:
        qdrant.get_collection("columnist_article_memory")
    except:
        qdrant.create_collection(
            collection_name="columnist_article_memory",
            vectors_config=VectorParams(
                size=1536,  # embedding size for text-embedding-3-small
                distance=Distance.COSINE
            )
        )


def store_article(qdrant, columnist, topic, article_text):
    """
    Stores each article in Qdrant.
    Over time, this forms the true evolving 'personality'.
    """

    if qdrant is None:
        return

    # Generate embedding
    embedding = client.embeddings.create(
        model="text-embedding-3-small",
        input=article_text
    ).data[0].embedding

    payload = {
        "columnist": columnist,
        "topic": topic,
        "article": article_text,
        "date": date.today().isoformat(),
        "type": "article_entry"
    }

    qdrant.upsert(
        collection_name="columnist_article_memory",
        points=[
            PointStruct(
                id=int.from_bytes(os.urandom(8), "big"),
                vector=embedding,
                payload=payload
            )
        ]
    )

    print(f"Stored article for {columnist}")
