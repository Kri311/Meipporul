import re

with open("frontend/src/app/page.jsx", "r") as f:
    content = f.read()

# Add use to import
content = content.replace("import { useEffect, useState } from 'react';", "import { useEffect, useState, use } from 'react';")

# Change Home signature and unwrap searchParams
replacement = """export default function Home(props) {
  const searchParams = use(props.searchParams);
  const lang = searchParams?.lang || 'en';"""

content = re.sub(
    r"export default function Home\(\{ searchParams \}\) \{\s*const \[events, setEvents\] = useState\(\[\]\);\s*const \[metadata, setMetadata\] = useState\(null\);\s*const lang = searchParams\?\.lang \|\| 'en';",
    """export default function Home(props) {
  const searchParams = use(props.searchParams);
  const [events, setEvents] = useState([]);
  const [metadata, setMetadata] = useState(null);
  const lang = searchParams?.lang || 'en';""",
    content
)

with open("frontend/src/app/page.jsx", "w") as f:
    f.write(content)
