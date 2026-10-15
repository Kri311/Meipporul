with open('extracted_events_page.txt', 'r') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if line.strip() == '"use client";':
        start_idx = i
    if start_idx != -1 and line.strip() == '}':
        end_idx = i

if start_idx != -1 and end_idx != -1:
    with open('frontend/src/app/events/[id]/page.jsx', 'w') as out:
        out.writelines(lines[start_idx:end_idx+1])
    print("Done")
