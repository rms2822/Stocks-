import json

def escape_for_script(json_text):
    return json_text.replace("</script", "<\\/script").replace("</SCRIPT", "<\\/SCRIPT")

dataset = json.load(open("data/dataset.json"))
analysis = json.load(open("data/analysis.json"))

dataset_json = escape_for_script(json.dumps(dataset))
analysis_json = escape_for_script(json.dumps(analysis))

template = open("dashboard_template.html").read()
out = template.replace("__DATASET_JSON__", dataset_json).replace("__ANALYSIS_JSON__", analysis_json)

with open("dashboard.html", "w") as f:
    f.write(out)

print(f"Wrote dashboard.html ({len(out)/1024:.1f} KB)")
