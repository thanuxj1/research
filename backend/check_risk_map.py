import urllib.request, json

res = urllib.request.urlopen('http://127.0.0.1:8000/api/v1/districts/risk-map')
data = json.loads(res.read().decode())
print(f"Total features: {len(data.get('features', []))}")
for f in data.get('features', []):
    p = f['properties']
    d_name = p.get('district')
    tier = p.get('risk_tier')
    cnt = p.get('report_count')
    scams = p.get('scam_report_count')
    recent_cnt = len(p.get('recent_reports', []))
    print(f"  [{d_name}] Tier: {tier} | Total Reports: {cnt} | Scam Reports: {scams} | Recent in payload: {recent_cnt}")
