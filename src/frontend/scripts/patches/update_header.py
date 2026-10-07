with open("frontend/src/components/Header.jsx", "r") as f:
    lines = f.readlines()

out = []
skip = False
for line in lines:
    if "href={`/blindspots?lang=${lang}`}" in line or "href={`/sources?lang=${lang}`}" in line:
        skip = True
        # backtrack to remove the Link opening tag
        while not out[-1].strip().startswith("<Link"):
            out.pop()
        out.pop() # remove <Link
    elif skip and "</Link>" in line:
        skip = False
        continue
    
    if not skip:
        out.append(line)

with open("frontend/src/components/Header.jsx", "w") as f:
    f.writelines(out)
