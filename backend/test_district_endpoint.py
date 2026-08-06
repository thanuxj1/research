import urllib.request, json

url = 'http://127.0.0.1:8000/api/v1/districts/Ampara/reports'
try:
    res = urllib.request.urlopen(url)
    data = json.loads(res.read().decode())
    print(f"Ampara reports returned: {data.get('total_reports')}")
    for r in data.get('reports', [])[:5]:
        print(f"  [{r.get('helpful_votes')} helpful] [{r.get('source')}] {r.get('title')[:60]} ({r.get('location')})")
except Exception as e:
    print(f"Error calling {url}: {e}")
