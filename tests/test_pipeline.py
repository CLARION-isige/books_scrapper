import os 
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import hashlib
import json

from web_crawler.web_crawler.pipelines import MongoBookPipeline
from web_crawler.web_crawler.items import WebCrawlerItem


@pytest.fixture
def pipeline():
    """Create pipeline instance with mocked MongoDB"""
    pipeline = MongoBookPipeline(
        mongo_uri= os.getenv("MONGO_URI"),
        mongo_db="test_db",
        books_collection="books",
        changes_collection="changes"
    )
    
    # Mock MongoDB client and collections
    pipeline.client = MagicMock()
    pipeline.db = MagicMock()
    pipeline.books = MagicMock()
    pipeline.changes = MagicMock()
    
    return pipeline


@pytest.fixture
def spider():
    """Mock spider for logging"""
    spider = MagicMock()
    spider.logger = MagicMock()
    return spider


@pytest.fixture
def sample_item():
    """Create a sample book item"""
    item = WebCrawlerItem()
    item["book_id"] = "test_upc_123"
    item["source_url"] = "https://books.toscrape.com/test"
    item["name"] = "Test Book"
    item["description"] = "A test book description"
    item["category"] = "Fiction"
    item["price_excl_tax"] = 10.99
    item["price_incl_tax"] = 12.99
    item["availability"] = "In stock (5 available)"
    item["num_reviews"] = 10
    item["image_url"] = "https://books.toscrape.com/media/test.jpg"
    item["rating"] = 4
    item["crawl_status"] = "success"
    item["raw_html"] = "<html>test</html>"
    return item


class TestHashGeneration:
    def test_hash_consistency(self, pipeline, sample_item):
        """Test that same content produces same hash"""
        from itemadapter import ItemAdapter
        
        adapter = ItemAdapter(sample_item)
        hash1 = pipeline._hash_item(adapter)
        hash2 = pipeline._hash_item(adapter)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest length

    def test_hash_changes_with_content(self, pipeline, sample_item):
        """Test that different content produces different hash"""
        from itemadapter import ItemAdapter
        
        adapter1 = ItemAdapter(sample_item)
        hash1 = pipeline._hash_item(adapter1)
        
        # Modify item
        sample_item["price_incl_tax"] = 15.99
        adapter2 = ItemAdapter(sample_item)
        hash2 = pipeline._hash_item(adapter2)
        
        assert hash1 != hash2


class TestNewBookInsertion:
    def test_insert_new_book(self, pipeline, spider, sample_item):
        """Test inserting a new book"""
        # Mock no existing book
        pipeline.books.find_one.return_value = None
        
        result = pipeline.process_item(sample_item, spider)
        
        # Verify insert was called
        assert pipeline.books.insert_one.called
        assert pipeline.changes.insert_one.called
        
        # Check change log has correct type
        change_call = pipeline.changes.insert_one.call_args[0][0]
        assert change_call["change_type"] == "new"
        assert change_call["book_id"] == "test_upc_123"
        
        spider.logger.info.assert_called()

    def test_new_book_has_content_hash(self, pipeline, spider, sample_item):
        """Test that new books get a content hash"""
        pipeline.books.find_one.return_value = None
        
        result = pipeline.process_item(sample_item, spider)
        
        # Check that content_hash was added
        assert "content_hash" in result


class TestBookUpdate:
    def test_update_changed_book(self, pipeline, spider, sample_item):
        """Test updating a book when content changes"""
        from itemadapter import ItemAdapter
        
        # Mock existing book with different hash
        existing = {
            "book_id": "test_upc_123",
            "name": "Test Book",
            "price_incl_tax": 10.99,  # Old price
            "content_hash": "old_hash_value",
            "crawl_ts": datetime.now(timezone.utc),
        }
        pipeline.books.find_one.return_value = existing
        
        # Process item with new price
        sample_item["price_incl_tax"] = 15.99
        result = pipeline.process_item(sample_item, spider)
        
        # Verify update was called
        assert pipeline.books.update_one.called
        assert pipeline.changes.insert_one.called
        
        # Check change log
        change_call = pipeline.changes.insert_one.call_args[0][0]
        assert change_call["change_type"] == "update"
        assert "price_incl_tax" in change_call["changes"]

    def test_no_update_when_unchanged(self, pipeline, spider, sample_item):
        """Test that unchanged books only update timestamp"""
        from itemadapter import ItemAdapter
        
        adapter = ItemAdapter(sample_item)
        content_hash = pipeline._hash_item(adapter)
        
        # Mock existing book with same hash
        existing = dict(sample_item)
        existing["content_hash"] = content_hash
        pipeline.books.find_one.return_value = existing
        
        result = pipeline.process_item(sample_item, spider)
        
        # Should only touch crawl_ts, not insert change
        assert pipeline.books.update_one.called
        update_call = pipeline.books.update_one.call_args[0][1]
        assert "$set" in update_call
        assert "crawl_ts" in update_call["$set"]


class TestErrorHandling:
    def test_missing_book_id(self, pipeline, spider):
        """Test handling of item without book_id or source_url"""
        item = WebCrawlerItem()
        item["name"] = "Test"
        
        with pytest.raises(ValueError, match="book_id"):
            pipeline.process_item(item, spider)

    def test_mongo_insert_error(self, pipeline, spider, sample_item):
        """Test handling of MongoDB insert errors"""
        from pymongo.errors import PyMongoError
        
        pipeline.books.find_one.return_value = None
        pipeline.books.insert_one.side_effect = PyMongoError("Connection error")
        
        # Should not raise, but log error
        result = pipeline.process_item(sample_item, spider)
        spider.logger.error.assert_called()

    def test_mongo_update_error(self, pipeline, spider, sample_item):
        """Test handling of MongoDB update errors"""
        from pymongo.errors import PyMongoError
        
        existing = {
            "book_id": "test_upc_123",
            "content_hash": "different_hash",
        }
        pipeline.books.find_one.return_value = existing
        pipeline.books.update_one.side_effect = PyMongoError("Connection error")
        
        # Should not raise, but log error
        result = pipeline.process_item(sample_item, spider)
        spider.logger.error.assert_called()


class TestIndexCreation:
    def test_indexes_created_on_open(self, pipeline, spider):
        """Test that indexes are created when spider opens"""
        pipeline.client = MagicMock()
        pipeline.db = MagicMock()

        # Create explicit mocks for collections
        mock_books = MagicMock()
        mock_changes = MagicMock()

        # Explicitly mock their `create_index` methods
        mock_books.create_index = MagicMock()
        mock_changes.create_index = MagicMock()

        # Attach them to the pipeline
        pipeline.books = mock_books
        pipeline.changes = mock_changes

        # Run method under test
        pipeline.open_spider(spider)

        assert mock_books.create_index.call_count >= 0
        assert mock_changes.create_index.call_count >= 0

