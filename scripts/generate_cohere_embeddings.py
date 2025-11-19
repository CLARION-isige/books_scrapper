import os
from dotenv import load_dotenv
from pymongo import MongoClient
import cohere

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
BOOKS_COL = os.getenv("MONGO_BOOKS_COLLECTION", "books")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

if not COHERE_API_KEY:
    raise RuntimeError("COHERE_API_KEY not set")

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
books = db[BOOKS_COL]

co = cohere.Client(COHERE_API_KEY)
# Only process books that don't have an embedding yet

def build_text(doc):
    parts = [
        doc.get("name") or "",
        f"Category: {doc.get('category') or ''}",
        doc.get("description") or "",
    ]
    return "\n\n".join(p for p in parts if p.strip())

def process_batch(batch_docs, books, co):
    texts = [build_text(d) for d in batch_docs]
    # If some docs have empty text, you may want to filter them out
    embeddings_response = co.embed(
        texts=texts,
        model="embed-english-v3.0",  # adjust if you prefer a different model
        input_type="search_document",
    )
    vectors = embeddings_response.embeddings

    for doc, vec in zip(batch_docs, vectors):
        books.update_one(
            {"_id": doc["_id"]},
            {"$set": {"embedding": vec}},
        )

cursor = books.find(
    {"embedding": {"$exists": False}},
    {"_id": 1, "name": 1, "category": 1, "description": 1},
)

BATCH_SIZE = 64

batch_docs = []
for doc in cursor:
    batch_docs.append(doc)
    if len(batch_docs) >= BATCH_SIZE:
        process_batch(batch_docs, books, co)
        batch_docs = []

if batch_docs:
    process_batch(batch_docs, books, co)

client.close()

