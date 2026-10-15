with open('extracted_page.txt', 'r') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if line.strip() == '"use client";':
        start_idx = i
    if start_idx != -1 and line.strip() == '}':
        end_idx = i

if start_idx != -1 and end_idx != -1:
    content = "".join(lines[start_idx:end_idx+1])
    # The original mapped over blindspots, let's keep it exactly as is
    with open('frontend/src/app/page.jsx', 'w') as out:
        out.write(content)
    print("Restored Home page!")
