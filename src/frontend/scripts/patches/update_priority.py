with open("frontend/src/app/page.jsx", "r") as f:
    content = f.read()

replacement = """  const PRIORITY = {
    'world_news': 1, 'world news': 1, 'உலக செய்திகள்': 1,
    'politics': 2, 'அரசியல்': 2,
    'economy': 3, 'பொருளாதாரம்': 3,
    'science_health': 4, 'அறிவியல் & சுகாதாரம்': 4,
    'education': 5, 'கல்வி': 5,
    'sports': 6, 'விளையாட்டு': 6,
    'crime_law': 7, 'குற்றம் & சட்டம்': 7,
    'general': 8, 'பொது செய்திகள்': 8,
    'news': 8, 'செய்திகள்': 8
  };"""

import re
content = re.sub(r'  const PRIORITY = \{.*?\};', replacement, content, flags=re.DOTALL)

with open("frontend/src/app/page.jsx", "w") as f:
    f.write(content)
