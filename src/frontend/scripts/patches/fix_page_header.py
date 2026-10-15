import re

for filename in ["frontend/src/app/page.jsx", "frontend/src/app/events/[id]/page.jsx"]:
    with open(filename, "r") as f:
        content = f.read()

    # Find where <Header is used
    if "<Header" in content:
        if filename.endswith("page.jsx") and "app/page.jsx" in filename:
            # We are in home page
            # Add uniqueTags computation
            tags_code = "const uniqueTags = [...new Set(events.flatMap(e => e.tags || []))].slice(0, 8);"
            content = content.replace("// Group events by topic", f"{tags_code}\n  // Group events by topic")
            content = content.replace("<Header lang={lang} activePage=\"home\" />", "<Header lang={lang} activePage=\"home\" tags={uniqueTags} />")
        else:
            # In events detail page, we just pass empty tags or event tags
            # Let's pass event tags if available
            content = content.replace("<Header lang={lang} activePage=\"home\" />", "<Header lang={lang} activePage=\"home\" tags={event?.tags || []} />")

        with open(filename, "w") as f:
            f.write(content)
