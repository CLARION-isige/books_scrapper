import re
from urllib.parse import urljoin

import scrapy
from scrapy.http import Response

from web_crawler.items import WebCrawlerItem


class BooksSpider(scrapy.Spider):
    name = "books"
    allowed_domains = ["books.toscrape.com"]
    start_urls = ["https://books.toscrape.com/"]

    custom_settings = {
        # politeness can be tuned via settings or env overrides
        # "DOWNLOAD_DELAY": 0.0,
    }

    def parse(self, response: Response):
        # navigate categories from sidebar
        for cat in response.css("div.side_categories ul li ul li a::attr(href)").getall():
            url = urljoin(response.url, cat)
            yield scrapy.Request(url, callback=self.parse_category)

    def parse_category(self, response: Response):
        # product tiles -> detail pages
        for href in response.css("article.product_pod h3 a::attr(href)").getall():
            url = urljoin(response.url, href)
            yield scrapy.Request(url, callback=self.parse_book)

        # pagination
        next_href = response.css("li.next a::attr(href)").get()
        if next_href:
            yield scrapy.Request(urljoin(response.url, next_href), callback=self.parse_category)

    def parse_book(self, response: Response):
        item = WebCrawlerItem()
        item["source_url"] = response.url
        item["raw_html"] = response.text

        # name
        item["name"] = response.css("div.product_main h1::text").get()

        # rating
        rating_class = response.css("div.product_main p.star-rating::attr(class)").get() or ""
        rating_match = re.search(r"star-rating\s+(\w+)", rating_class)
        rating_map = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
        item["rating"] = rating_map.get(rating_match.group(1), None) if rating_match else None

        # product table values (UPC as book_id, prices, availability, reviews)
        table = {
            (row.css("th::text").get() or "").strip(): (row.css("td::text").get() or "").strip()
            for row in response.css("table.table.table-striped tr")
        }
        # book_id -> UPC is stable identifier on the site
        item["book_id"] = table.get("UPC")

        def parse_price(text):
            # format like '£51.77'
            if not text:
                return None
            return float(text.replace("£", "").strip())

        item["price_excl_tax"] = parse_price(table.get("Price (excl. tax)"))
        item["price_incl_tax"] = parse_price(table.get("Price (incl. tax)"))

        # availability like 'In stock (19 available)'
        item["availability"] = table.get("Availability")

        # Number of reviews is an integer
        try:
            item["num_reviews"] = int(table.get("Number of reviews", "0"))
        except ValueError:
            item["num_reviews"] = None

        # description
        desc_sel = response.xpath('//div[@id="product_description"]/following-sibling::p[1]/text()')
        item["description"] = desc_sel.get()

        # category from breadcrumb
        cat_text = response.css("ul.breadcrumb li:nth-child(3) a::text").get()
        item["category"] = cat_text

        # image URL
        rel_img = response.css("div.item.active img::attr(src)").get()
        item["image_url"] = urljoin(response.url, rel_img) if rel_img else None

        # mark success; timestamps and content_hash handled in pipeline
        item["crawl_status"] = "success"

        yield item
