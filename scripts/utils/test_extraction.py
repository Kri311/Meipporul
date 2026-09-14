import feedparser
import requests
import trafilatura

# 1. Test News18 Tamil Encoding
print("--- News18 Tamil Encoding Test ---")
url = "https://tamil.news18.com/commonfeeds/v1/tam/rss/latest.xml"
feed = feedparser.parse(url)
if feed.entries:
    entry = feed.entries[0]
    link = entry.link
    print(f"URL: {link}")
    resp = requests.get(link)
    # Check default encoding
    print(f"Requests guessed encoding: {resp.encoding}")
    print(f"Apparent encoding: {resp.apparent_encoding}")
    
    # Try Trafilatura with text (wrong encoding) vs bytes
    ext_text = trafilatura.extract(resp.text)
    ext_bytes = trafilatura.extract(resp.content)
    
    print("Text (resp.text) slice:", repr(ext_text[:100] if ext_text else ""))
    print("Bytes (resp.content) slice:", repr(ext_bytes[:100] if ext_bytes else ""))

# 2. Test Indian Express 
print("\n--- Indian Express Test ---")
url = "https://indianexpress.com/section/india/feed/"
feed = feedparser.parse(url)
if feed.entries:
    entry = feed.entries[0]
    print(f"Title: {entry.title}")
    raw_content = ""
    if hasattr(entry, 'content'):
        raw_content = entry.content[0].value
    elif hasattr(entry, 'description'):
        raw_content = entry.description
    print(f"Raw Text length: {len(raw_content)}")
    print(f"Raw Text slice: {raw_content[:200]}")
    
    link = entry.link
    resp = requests.get(link)
    ext_bytes = trafilatura.extract(resp.content)
    print("Trafilatura Extracted slice:", repr(ext_bytes[-200:] if ext_bytes else ""))

