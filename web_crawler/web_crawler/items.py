# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class WebCrawlerItem(scrapy.Item):
    book_id = scrapy.Field()
    source_url = scrapy.Field()

    name = scrapy.Field()
    description = scrapy.Field()
    category = scrapy.Field()
    price_excl_tax = scrapy.Field()
    price_incl_tax = scrapy.Field()
    availability = scrapy.Field()
    num_reviews = scrapy.Field()
    image_url = scrapy.Field()
    rating = scrapy.Field()

    content_hash = scrapy.Field()

    crawl_status = scrapy.Field()
    crawl_ts = scrapy.Field()

    raw_html = scrapy.Field()
