"""
Async Book Crawler using httpx
Alternative to Scrapy for async-first crawling
"""
import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# Pydantic Models
class Book(BaseModel):
    """Book schema with Pydantic validation"""
    book_id: str = Field(..., description="Unique identifier (UPC)")
    source_url: str = Field(..., description="Source URL of the book page")
    name: Optional[str] = Field(None, description="Book title")
    description: Optional[str] = Field(None, description="Book description")
    category: Optional[str] = Field(None, description="Book category")
    price_excl_tax: Optional[float] = Field(None, ge=0, description="Price excluding tax")
    price_incl_tax: Optional[float] = Field(None, ge=0, description="Price including tax")
    availability: Optional[str] = Field(None, description="Availability status")
    num_reviews: Optional[int] = Field(None, ge=0, description="Number of reviews")
    image_url: Optional[str] = Field(None, description="Cover image URL")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Star rating")
    crawl_status: str = Field(default="success", description="Crawl status")
    crawl_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: Optional[str] = Field(None, description="Hash for change detection")
    raw_html: Optional[str] = Field(None, description="Raw HTML snapshot")


class AsyncBookCrawler:
    """Async web crawler for books.toscrape.com"""
    
    def __init__(
        self,
        mongo_uri: str,
        mongo_db: str,
        books_collection: str = "books",
        changes_collection: str = "changes",
        concurrent_requests: int = 10,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        self.base_url = "https://books.toscrape.com"
        self.mongo_uri = mongo_uri
        self.mongo_db_name = mongo_db
        self.books_collection_name = books_collection
        self.changes_collection_name = changes_collection
        self.concurrent_requests = concurrent_requests
        self.timeout = timeout
        self.max_retries = max_retries
        
        self.client = None
        self.db = None
        self.semaphore = asyncio.Semaphore(concurrent_requests)
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.client = AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client[self.mongo_db_name]
        
        # Create indexes
        await self.db[self.books_collection_name].create_index("book_id", unique=True)
        await self.db[self.books_collection_name].create_index([("category", 1), ("price_incl_tax", 1), ("rating", 1)])
        await self.db[self.changes_collection_name].create_index("book_id")
        await self.db[self.changes_collection_name].create_index("changed_at")
        
        logger.info("Connected to MongoDB")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.client:
            self.client.close()
            logger.info("Closed MongoDB connection")
    
    async def fetch_with_retry(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        """Fetch URL with retry logic"""
        for attempt in range(self.max_retries):
            try:
                async with self.semaphore:
                    response = await client.get(url, timeout=self.timeout)
                    response.raise_for_status()
                    return response.text
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Retry {attempt + 1}/{self.max_retries} for {url}: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to fetch {url} after {self.max_retries} attempts: {e}")
                    return None
        return None
    
    def parse_book_detail(self, html: str, url: str) -> Optional[Book]:
        """Parse book detail page"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract fields
            name = soup.select_one("div.product_main h1")
            name = name.get_text(strip=True) if name else None
            
            # Rating
            rating_elem = soup.select_one("div.product_main p.star-rating")
            rating = None
            if rating_elem:
                rating_class = rating_elem.get("class", [])
                rating_map = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
                for cls in rating_class:
                    if cls in rating_map:
                        rating = rating_map[cls]
                        break
            
            # Table data
            table_data = {}
            for row in soup.select("table.table.table-striped tr"):
                th = row.select_one("th")
                td = row.select_one("td")
                if th and td:
                    key = th.get_text(strip=True)
                    value = td.get_text(strip=True)
                    table_data[key] = value
            
            book_id = table_data.get("UPC")
            if not book_id:
                logger.warning(f"No UPC found for {url}")
                return None
            
            # Prices
            def parse_price(text):
                if not text:
                    return None
                text = text.replace("£", "").strip()
                try:
                    return float(text)
                except ValueError:
                    return None
            
            price_excl_tax = parse_price(table_data.get("Price (excl. tax)"))
            price_incl_tax = parse_price(table_data.get("Price (incl. tax)"))
            
            # Availability
            availability = table_data.get("Availability")
            
            # Reviews
            num_reviews = 0
            try:
                num_reviews = int(table_data.get("Number of reviews", "0"))
            except ValueError:
                pass
            
            # Description
            desc_elem = soup.select_one('div#product_description + p')
            description = desc_elem.get_text(strip=True) if desc_elem else None
            
            # Category from breadcrumb
            breadcrumb = soup.select("ul.breadcrumb li")
            category = None
            if len(breadcrumb) >= 3:
                category_elem = breadcrumb[2].select_one("a")
                if category_elem:
                    category = category_elem.get_text(strip=True)
            
            # Image
            img_elem = soup.select_one("div.item.active img")
            image_url = None
            if img_elem:
                img_src = img_elem.get("src")
                if img_src:
                    image_url = urljoin(url, img_src)
            
            book = Book(
                book_id=book_id,
                source_url=url,
                name=name,
                description=description,
                category=category,
                price_excl_tax=price_excl_tax,
                price_incl_tax=price_incl_tax,
                availability=availability,
                num_reviews=num_reviews,
                image_url=image_url,
                rating=rating,
                raw_html=html
            )
            
            # Compute content hash
            book.content_hash = self._compute_hash(book)
            
            return book
            
        except Exception as e:
            logger.error(f"Error parsing {url}: {e}")
            return None
    
    def _compute_hash(self, book: Book) -> str:
        """Compute content hash for change detection"""
        fields = {
            "name": book.name,
            "description": book.description,
            "category": book.category,
            "price_excl_tax": book.price_excl_tax,
            "price_incl_tax": book.price_incl_tax,
            "availability": book.availability,
            "num_reviews": book.num_reviews,
            "image_url": book.image_url,
            "rating": book.rating,
        }
        encoded = json.dumps(fields, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
    
    async def save_book(self, book: Book):
        """Save or update book in database with change detection"""
        books_col = self.db[self.books_collection_name]
        changes_col = self.db[self.changes_collection_name]
        
        existing = await books_col.find_one({"book_id": book.book_id}, projection={"_id": False})
        
        book_dict = book.model_dump()
        
        if not existing:
            # New book
            await books_col.insert_one(book_dict)
            await changes_col.insert_one({
                "book_id": book.book_id,
                "change_type": "new",
                "changes": {k: v for k, v in book_dict.items() if k not in {"raw_html"}},
                "changed_at": datetime.now(timezone.utc),
                "source_url": book.source_url,
            })
            logger.info(f"Inserted new book: {book.book_id}")
        else:
            # Check for changes
            if existing.get("content_hash") != book.content_hash:
                # Compute diffs
                ignored = {"crawl_ts", "raw_html", "content_hash", "_id"}
                diffs = {}
                for k, new_val in book_dict.items():
                    if k in ignored:
                        continue
                    old_val = existing.get(k)
                    if new_val != old_val:
                        diffs[k] = {"old": old_val, "new": new_val}
                
                await books_col.update_one({"book_id": book.book_id}, {"$set": book_dict})
                await changes_col.insert_one({
                    "book_id": book.book_id,
                    "change_type": "update",
                    "changes": diffs,
                    "changed_at": datetime.now(timezone.utc),
                    "source_url": book.source_url,
                })
                logger.info(f"Updated book: {book.book_id} - changes: {list(diffs.keys())}")
            else:
                # No changes, just update timestamp
                await books_col.update_one(
                    {"book_id": book.book_id},
                    {"$set": {"crawl_ts": book.crawl_ts, "raw_html": book.raw_html}}
                )
    
    async def crawl_book_page(self, client: httpx.AsyncClient, url: str):
        """Crawl a single book page"""
        html = await self.fetch_with_retry(client, url)
        if html:
            book = self.parse_book_detail(html, url)
            if book:
                await self.save_book(book)
    
    async def get_book_urls_from_category(self, client: httpx.AsyncClient, category_url: str) -> List[str]:
        """Get all book URLs from a category with pagination"""
        book_urls = []
        current_url = category_url
        
        while current_url:
            html = await self.fetch_with_retry(client, current_url)
            if not html:
                break
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract book links
            for link in soup.select("article.product_pod h3 a"):
                href = link.get("href")
                if href:
                    book_url = urljoin(current_url, href)
                    book_urls.append(book_url)
            
            # Check for next page
            next_link = soup.select_one("li.next a")
            if next_link:
                next_href = next_link.get("href")
                current_url = urljoin(current_url, next_href) if next_href else None
            else:
                current_url = None
        
        logger.info(f"Found {len(book_urls)} books in category")
        return book_urls
    
    async def get_category_urls(self, client: httpx.AsyncClient) -> List[str]:
        """Get all category URLs from homepage"""
        html = await self.fetch_with_retry(client, self.base_url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        category_urls = []
        
        for link in soup.select("div.side_categories ul li ul li a"):
            href = link.get("href")
            if href:
                category_url = urljoin(self.base_url, href)
                category_urls.append(category_url)
        
        logger.info(f"Found {len(category_urls)} categories")
        return category_urls
    
    async def crawl(self):
        """Main crawl method"""
        logger.info("Starting async crawl...")
        start_time = datetime.now()
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Get categories
            category_urls = await self.get_category_urls(client)
            
            # Get all book URLs from all categories
            all_book_urls = []
            for cat_url in category_urls:
                book_urls = await self.get_book_urls_from_category(client, cat_url)
                all_book_urls.extend(book_urls)
            
            # Remove duplicates
            all_book_urls = list(set(all_book_urls))
            logger.info(f"Total unique books to crawl: {len(all_book_urls)}")
            
            # Crawl all books concurrently
            tasks = [self.crawl_book_page(client, url) for url in all_book_urls]
            await asyncio.gather(*tasks)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Crawl completed in {elapsed:.2f} seconds")


async def main():
    """Run async crawler"""
    mongo_uri = os.getenv("MONGO_URI")
    mongo_db = os.getenv("MONGO_DB")
    books_col = os.getenv("MONGO_BOOKS_COLLECTION")
    changes_col = os.getenv("MONGO_CHANGES_COLLECTION")
    
    async with AsyncBookCrawler(
        mongo_uri=mongo_uri,
        mongo_db=mongo_db,
        books_collection=books_col,
        changes_collection=changes_col,
        concurrent_requests=10,
        timeout=30.0,
        max_retries=3
    ) as crawler:
        await crawler.crawl()


if __name__ == "__main__":
    asyncio.run(main())
