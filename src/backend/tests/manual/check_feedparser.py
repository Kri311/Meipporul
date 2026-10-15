import feedparser
feed = feedparser.parse("https://tamil.news18.com/commonfeeds/v1/tam/rss/national.xml")
print(feed.entries[0].title)
