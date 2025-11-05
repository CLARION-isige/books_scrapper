import hashlib
import json
import os
from datetime import datetime, timezone

from itemadapter import ItemAdapter
from pymongo import MongoClient
from pymongo.errors import PyMongoError


class MongoBookPipeline:
     @classmethod
     def from_crawler(cls, crawler):
         settings = crawler.settings
         return cls(
             mongo_uri=settings.get("MONGO_URI", os.getenv("MONGO_URI")),
             mongo_db=settings.get("MONGO_DB", os.getenv("MONGO_DB", 'books_db')),
             books_collection=settings.get("MONGO_BOOKS_COLLECTION", os.getenv("MONGO_BOOKS_COLLECTION", "books")),
             changes_collection=settings.get("MONGO_CHANGES_COLLECTION", os.getenv("MONGO_CHANGES_COLLECTION", "changes")),
         )

     def __init__(self, mongo_uri: str, mongo_db: str, books_collection: str, changes_collection: str):
         self.mongo_uri = mongo_uri
         self.mongo_db_name = mongo_db
         self.books_collection_name = books_collection
         self.changes_collection_name = changes_collection
         self.client = None
         self.db = None
         self.books = None
         self.changes = None

     def open_spider(self, spider):
         self.client = MongoClient(self.mongo_uri)
         self.db = self.client[self.mongo_db_name]
         self.books = self.db[self.books_collection_name]
         self.changes = self.db[self.changes_collection_name]
         # Ensure indexes for deduplication and efficient querying
         try:
             self.books.create_index("book_id", unique=True)
             self.books.create_index([("category", 1), ("price_incl_tax", 1), ("rating", 1)])
             self.books.create_index("content_hash")
             self.books.create_index("crawl_ts")
             self.changes.create_index("book_id")
             self.changes.create_index("changed_at")
         except PyMongoError as e:
             spider.logger.error(f"Error ensuring indexes: {e}")

     def close_spider(self, spider):
         if self.client:
             self.client.close()

     def _hash_item(self, adapter: ItemAdapter) -> str:
         # Build a stable dict of relevant fields for change detection
         fields = {
             "name": adapter.get("name"),
             "description": adapter.get("description"),
             "category": adapter.get("category"),
             "price_excl_tax": adapter.get("price_excl_tax"),
             "price_incl_tax": adapter.get("price_incl_tax"),
             "availability": adapter.get("availability"),
             "num_reviews": adapter.get("num_reviews"),
             "image_url": adapter.get("image_url"),
             "rating": adapter.get("rating"),
         }
         encoded = json.dumps(fields, sort_keys=True, ensure_ascii=False).encode("utf-8")
         return hashlib.sha256(encoded).hexdigest()

     def process_item(self, item, spider):
         adapter = ItemAdapter(item)

         # Required identifiers
         book_id = adapter.get("book_id") or adapter.get("source_url")
         if not book_id:
             raise ValueError("Item missing 'book_id' or 'source_url'")

         now = datetime.now(timezone.utc)

         # Compute content hash for change detection
         content_hash = self._hash_item(adapter)
         adapter["content_hash"] = content_hash
         adapter.setdefault("crawl_status", "success")
         adapter["crawl_ts"] = now

         # Normalize to dict for Mongo
         doc = adapter.asdict()

         # Existing doc
         existing = self.books.find_one({"book_id": book_id}, projection={"_id": False})

         if not existing:
             # New insert
             doc["book_id"] = book_id
             try:
                 self.books.insert_one(doc)
                 self.changes.insert_one({
                     "book_id": book_id,
                     "change_type": "new",
                     "changes": {k: doc.get(k) for k in doc.keys() if k not in {"raw_html"}},
                     "changed_at": now,
                     "source_url": adapter.get("source_url"),
                 })
                 spider.logger.info(f"Inserted new book {book_id}")
             except PyMongoError as e:
                 spider.logger.error(f"Mongo insert error for {book_id}: {e}")
         else:
             # Compare hashes for change detection
             if existing.get("content_hash") != content_hash:
                 # Compute field-level diffs (excluding raw_html and timestamps)
                 ignored = {"crawl_ts", "raw_html"}
                 diffs = {}
                 for k, new_val in doc.items():
                     if k in ignored:
                         continue
                     old_val = existing.get(k)
                     if new_val != old_val:
                         diffs[k] = {"old": old_val, "new": new_val}
                 try:
                     self.books.update_one({"book_id": book_id}, {"$set": doc})
                     self.changes.insert_one({
                         "book_id": book_id,
                         "change_type": "update",
                         "changes": diffs,
                         "changed_at": now,
                         "source_url": adapter.get("source_url"),
                     })
                     spider.logger.info(f"Updated book {book_id} with changes: {list(diffs.keys())}")
                 except PyMongoError as e:
                     spider.logger.error(f"Mongo update error for {book_id}: {e}")
             else:
                 # Update crawl_ts and potentially raw_html for snapshot freshness
                 try:
                     self.books.update_one({"book_id": book_id}, {"$set": {"crawl_ts": now, "raw_html": doc.get("raw_html")}})
                 except PyMongoError as e:
                     spider.logger.error(f"Mongo touch error for {book_id}: {e}")

         return item
