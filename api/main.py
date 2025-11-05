import os
import time
from typing import List, Optional
from contextlib import asynccontextmanager
from datetime import datetime

import orjson
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from bson import ObjectId

load_dotenv()

API_KEY = os.getenv("X-API-KEY")
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
BOOKS_COL = os.getenv("MONGO_BOOKS_COLLECTION")
CHANGES_COL = os.getenv("MONGO_CHANGES_COLLECTION")
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR"))


class ORJSONResponseCustom(ORJSONResponse):
    def render(self, content: any) -> bytes:
        return orjson.dumps(content)


def _convert_bson(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, list):
        return [_convert_bson(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _convert_bson(v) for k, v in obj.items()}
    return obj


# ---- Lifespan handler replacing on_event ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mongo = AsyncIOMotorClient(MONGO_URI)
    app.state.db = app.state.mongo[MONGO_DB]
    print("✅ Connected to MongoDB")

    yield  # Application runs here

    app.state.mongo.close()
    print("🛑 MongoDB connection closed")


app = FastAPI(
    title="Books Monitor API",
    default_response_class=ORJSONResponseCustom,
    lifespan=lifespan,
)


# ---- Rate Limiting ----
_rate_store = {}


def get_api_key(request: Request):
    api_key = request.headers.get("X-API-KEY")
    
    if api_key != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    bucket = int(time.time() // 3600)
    key = (api_key, bucket)
    cnt = _rate_store.get(key, 0)
    if cnt >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _rate_store[key] = cnt + 1

    return api_key


# ---- Pydantic Models ----
class BookOut(BaseModel):
    book_id: str
    source_url: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price_excl_tax: Optional[float] = None
    price_incl_tax: Optional[float] = None
    availability: Optional[str] = None
    num_reviews: Optional[int] = None
    image_url: Optional[str] = None
    rating: Optional[int] = None
    crawl_ts: Optional[datetime] = None


class ChangeOut(BaseModel):
    book_id: str
    change_type: str
    changes: dict
    changed_at: datetime


# ---- Routes ----
@app.get("/books", response_model=List[BookOut])
async def list_books(
    category: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    rating: Optional[int] = Query(None, ge=1, le=5),
    sort_by: Optional[str] = Query(None, pattern="^(rating|price|reviews)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = {}
    if category:
        q["category"] = category
    if min_price is not None or max_price is not None:
        price_q = {}
        if min_price is not None:
            price_q["$gte"] = min_price
        if max_price is not None:
            price_q["$lte"] = max_price
        q["price_incl_tax"] = price_q
    if rating is not None:
        q["rating"] = rating

    sort = None
    if sort_by == "rating":
        sort = [("rating", -1)]
    elif sort_by == "price":
        sort = [("price_incl_tax", 1)]
    elif sort_by == "reviews":
        sort = [("num_reviews", -1)]

    skip = (page - 1) * page_size
    cursor = app.state.db[BOOKS_COL].find(q, {"_id": 0}).skip(skip).limit(page_size)
    if sort:
        cursor = cursor.sort(sort)
    return [doc async for doc in cursor]


@app.get("/books/{book_id}", response_model=BookOut)
async def get_book(book_id: str):
    doc = await app.state.db[BOOKS_COL].find_one({"book_id": book_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Book not found")
    return doc


@app.get("/changes", response_model=List[ChangeOut])
async def get_changes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    skip = (page - 1) * page_size
    cursor = (
        app.state.db[CHANGES_COL]
        .find({}, {"_id": 0})
        .sort([("changed_at", -1)])
        .skip(skip)
        .limit(page_size)
    )
    docs = [doc async for doc in cursor]
    return [_convert_bson(d) for d in docs]


