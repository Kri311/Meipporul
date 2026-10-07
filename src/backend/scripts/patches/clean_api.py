with open("src/backend/api.py", "r") as f:
    lines = f.readlines()

out_lines = []
skip = False
for line in lines:
    if '@app.get("/blindspots/")' in line or '@app.get("/events/{event_id}/blindspots")' in line or '@app.get("/events/{event_id}/matrix")' in line or '@app.get("/sources")' in line or '@app.get("/sources/{id}")' in line:
        skip = True
    elif skip and line.startswith('@app.get'):
        skip = False
    elif skip and line.startswith('if __name__ == "__main__":'):
        skip = False
    
    if not skip:
        out_lines.append(line)

with open("src/backend/api.py", "w") as f:
    f.writelines(out_lines)
