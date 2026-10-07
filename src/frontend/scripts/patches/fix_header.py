with open("frontend/src/components/Header.jsx", "r") as f:
    content = f.read()

# Make Header sync and not fetch
content = content.replace("export default async function Header({", "export default function Header({")
content = content.replace("import { fetchEvents } from '@/lib/api';", "")
content = content.replace("import { fetchEvents } from '../lib/api';", "")

# Remove the try/catch fetchEvents
import re
content = re.sub(r"let events = \[\];\s*try \{.*?catch.*?\}\s*", "", content, flags=re.DOTALL)
content = re.sub(r"const allTags = events\.flatMap\(e => e\.tags \|\| \[\]\);\s*const uniqueTags = \[...new Set\(allTags\)\].slice\(0, 8\);", "const uniqueTags = tags || [];", content)

# Also Header signature to accept tags
content = content.replace("activePage = 'home', selectedTag = null }) {", "activePage = 'home', selectedTag = null, tags = [] }) {")

# Update trending rendering to format tags nicely
content = content.replace("{tag}", "{tag.replace(/_/g, ' ')}")

with open("frontend/src/components/Header.jsx", "w") as f:
    f.write(content)
