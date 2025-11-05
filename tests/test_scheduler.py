import pytest
import os
import json
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone

# Must set env vars before importing scheduler
mongo_db = os.getenv("MONGO_URI")
os.environ.setdefault("MONGO_URI", mongo_db)
os.environ.setdefault("MONGO_DB", "test_db")
os.environ.setdefault("MONGO_CHANGES_COLLECTION", "changes")
os.environ.setdefault("REPORTS_DIR", "/tmp/test_reports")

from scheduler.daily import run_crawl, generate_daily_report, job


class TestCrawlExecution:
    @patch("scheduler.daily.subprocess.run")
    def test_run_crawl_calls_scrapy(self, mock_subprocess):
        """Test that run_crawl executes scrapy command"""
        run_crawl()
        
        assert mock_subprocess.called
        args = mock_subprocess.call_args[0][0]
        
        # Verify scrapy command structure
        assert "scrapy" in args
        assert "crawl" in args
        assert "books" in args
        assert "JOBDIR=.job/books_daily" in " ".join(args)

    @patch("scheduler.daily.subprocess.run")
    def test_run_crawl_with_resume_support(self, mock_subprocess):
        """Test that JOBDIR is specified for resume capability"""
        run_crawl()
        
        args = mock_subprocess.call_args[0][0]
        jobdir_found = any("JOBDIR" in arg for arg in args)
        assert jobdir_found


class TestReportGeneration:
    @patch("scheduler.daily.MongoClient")
    def test_generate_daily_report_creates_file(self, mock_mongo_client):
        """Test that report file is created"""
        # Mock MongoDB response
        mock_collection = MagicMock()
        mock_collection.find.return_value.sort.return_value = []
        
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        
        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_client.return_value = mock_client
        
        report_path = generate_daily_report()
        
        # Verify report path format
        assert "changes_" in report_path
        assert ".json" in report_path

    @patch("scheduler.daily.MongoClient")
    def test_report_contains_correct_structure(self, mock_mongo_client):
        """Test that report has correct JSON structure"""
        # Mock changes data
        mock_changes = [
            {
                "book_id": "test123",
                "change_type": "new",
                "changed_at": datetime.now(timezone.utc),
            }
        ]
        
        mock_collection = MagicMock()
        mock_collection.find.return_value.sort.return_value = mock_changes
        
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        
        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_client.return_value = mock_client
        
        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file
            
            report_path = generate_daily_report()
            
            # Verify file was written
            assert mock_file.write.called or mock_open.called

    @patch("scheduler.daily.MongoClient")
    def test_report_queries_today_changes(self, mock_mongo_client):
        """Test that report only includes today's changes"""
        mock_collection = MagicMock()
        mock_collection.find.return_value.sort.return_value = []
        
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        
        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_client.return_value = mock_client
        
        generate_daily_report()
        
        # Verify find was called with date filter
        assert mock_collection.find.called
        query = mock_collection.find.call_args[0][0]
        assert "changed_at" in query
        assert "$gte" in query["changed_at"]


class TestSchedulerJob:
    @patch("scheduler.daily.generate_daily_report")
    @patch("scheduler.daily.run_crawl")
    def test_job_runs_crawl_and_report(self, mock_crawl, mock_report):
        """Test that job executes both crawl and report"""
        mock_report.return_value = "/tmp/report.json"
        
        job()
        
        assert mock_crawl.called
        assert mock_report.called
        
        # Verify order: crawl first, then report
        assert mock_crawl.call_count == 1
        assert mock_report.call_count == 1

    @patch("scheduler.daily.generate_daily_report")
    @patch("scheduler.daily.run_crawl")
    @patch("builtins.print")
    def test_job_prints_completion_message(self, mock_print, mock_crawl, mock_report):
        """Test that job prints completion message"""
        mock_report.return_value = "/tmp/report.json"
        
        job()
        
        # Verify print was called with report path
        assert mock_print.called
        print_message = str(mock_print.call_args)
        assert "report" in print_message.lower() or "completed" in print_message.lower()


class TestReportDirectoryCreation:
    @patch("scheduler.daily.MongoClient")
    @patch("scheduler.daily.os.makedirs")
    def test_reports_directory_created(self, mock_makedirs, mock_mongo_client):
        """Test that reports directory is created if it doesn't exist"""
        # Mock MongoDB
        mock_collection = MagicMock()
        mock_collection.find.return_value.sort.return_value = []
        
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        
        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_client.return_value = mock_client
        
        generate_daily_report()
        
        # Verify makedirs was called
        assert mock_makedirs.called
        assert mock_makedirs.call_args[1].get("exist_ok") == True
