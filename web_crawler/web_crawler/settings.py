import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Scrapy settings for web_crawler project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "web_crawler"

SPIDER_MODULES = ["web_crawler.spiders"]
NEWSPIDER_MODULE = "web_crawler.spiders"

ADDONS = {}


# Crawl responsibly by identifying yourself (and your website) on the user-agent
# USER_AGENT = "web_crawler (+http://www.yourdomain.com)"

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Concurrency and throttling settings
CONCURRENT_REQUESTS = int(os.getenv("SCRAPY_CONCURRENT_REQUESTS", "16"))
CONCURRENT_REQUESTS_PER_DOMAIN = int(os.getenv("SCRAPY_CONCURRENT_REQUESTS_PER_DOMAIN", "8"))
DOWNLOAD_DELAY = float(os.getenv("SCRAPY_DOWNLOAD_DELAY", "0.0"))

# Retries and timeouts
RETRY_ENABLED = True
RETRY_TIMES = int(os.getenv("SCRAPY_RETRY_TIMES", "3"))
DOWNLOAD_TIMEOUT = int(os.getenv("SCRAPY_DOWNLOAD_TIMEOUT", "30"))

# Cookies
COOKIES_ENABLED = False

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "web_crawler.middlewares.WebCrawlerSpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    "web_crawler.middlewares.WebCrawlerDownloaderMiddleware": 543,
#}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

 # Configure item pipelines
 # See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
ITEM_PIPELINES = {
    "web_crawler.pipelines.MongoBookPipeline": 300,
}

 # Enable and configure the AutoThrottle extension (disabled by default)
 # See https://docs.scrapy.org/en/latest/topics/autothrottle.html
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = float(os.getenv("SCRAPY_AUTOTHROTTLE_START_DELAY", "0.5"))
AUTOTHROTTLE_MAX_DELAY = float(os.getenv("SCRAPY_AUTOTHROTTLE_MAX_DELAY", "10"))
AUTOTHROTTLE_TARGET_CONCURRENCY = float(os.getenv("SCRAPY_AUTOTHROTTLE_TARGET_CONCURRENCY", "2.0"))
AUTOTHROTTLE_DEBUG = False

 # Enable and configure HTTP caching (disabled by default)
 # See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
HTTPCACHE_ENABLED = os.getenv("SCRAPY_HTTPCACHE_ENABLED", "false").lower() == "true"
HTTPCACHE_EXPIRATION_SECS = int(os.getenv("SCRAPY_HTTPCACHE_EXPIRATION_SECS", "0"))
HTTPCACHE_DIR = os.getenv("SCRAPY_HTTPCACHE_DIR", "httpcache")
HTTPCACHE_IGNORE_HTTP_CODES = []
HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

 # Mongo settings via environment
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
MONGO_BOOKS_COLLECTION = os.getenv("MONGO_BOOKS_COLLECTION")
MONGO_CHANGES_COLLECTION = os.getenv("MONGO_CHANGES_COLLECTION")

# Logging configuration
LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "logs", f"crawl_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log")
LOG_LEVEL = os.getenv("SCRAPY_LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_DATEFORMAT = "%Y-%m-%d %H:%M:%S"

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"
