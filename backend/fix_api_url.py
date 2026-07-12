content = open("dashboard.html", encoding="utf-8").read()

# Replace hardcoded localhost with dynamic host detection
old = 'const API = "http://localhost:8000";'
new = 'const API = window.location.hostname === "localhost" ? "http://localhost:8000" : window.location.origin;'

if old in content:
    content = content.replace(old, new)
    print("Fixed API URL to be dynamic")
else:
    print("Pattern not found")
    import re
    matches = re.findall(r'const API.*?;', content)
    print("Found:", matches[:3])

open("dashboard.html", "w", encoding="utf-8").write(content)
