with open("frontend/src/app/page.jsx", "r") as f:
    content = f.read()

content = content.replace(
    "const uniqueTags = ['world_news', 'politics', 'economy', 'science_health', 'sports', 'crime_law', 'education', 'general'];",
    "const uniqueTags = [...new Set(events.flatMap(e => e.tags || []))].slice(0, 8);"
)

with open("frontend/src/app/page.jsx", "w") as f:
    f.write(content)
