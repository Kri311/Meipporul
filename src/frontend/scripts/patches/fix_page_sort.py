import re

with open("frontend/src/app/page.jsx", "r") as f:
    content = f.read()

replacement = """
  const selectedTag = searchParams?.tag || null;

  // Group events by topic
  const groupedEvents = events.reduce((acc, event) => {
    const t = event.topic || 'General';
    if (!acc[t]) acc[t] = [];
    acc[t].push(event);
    return acc;
  }, {});

  const PRIORITY = {
    'world_news': 1,
    'politics': 2,
    'economy': 3,
    'science_health': 4,
    'education': 5,
    'sports': 6,
    'crime_law': 7,
    'general': 8
  };

  const sortedTopics = Object.entries(groupedEvents)
    .filter(([topic]) => !selectedTag || topic === selectedTag)
    .sort(([a], [b]) => {
      const pA = PRIORITY[a] || 99;
      const pB = PRIORITY[b] || 99;
      return pA - pB;
    });
"""

# Replace from `// Group events by topic` to `return (`
content = re.sub(r'  const uniqueTags = \[...new Set\(events.flatMap\(e => e.tags \|\| \[\]\)\)\].slice\(0, 8\);\n  // Group events by topic.*?return \(', 
    """  const uniqueTags = ['world_news', 'politics', 'economy', 'science_health', 'sports', 'crime_law', 'education', 'general'];""" + replacement + "\n  return (", content, flags=re.DOTALL)

content = content.replace("Object.entries(groupedEvents).map(([topic, topicEvents])", "sortedTopics.map(([topic, topicEvents])")

with open("frontend/src/app/page.jsx", "w") as f:
    f.write(content)
