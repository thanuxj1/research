
import requests
import json

def test_heatmap():
    url = "http://localhost:8000/api/v1/safety/heatmap"
    
    # 1. Test General
    print("--- General ---")
    resp = requests.get(url, params={"demographic": "General"})
    data = resp.json()
    print(f"Total zones: {len(data)}")
    for z in data:
        status = "MODERATE" if 0.2 <= z['risk_score'] < 0.7 else "HIGH" if z['risk_score'] >= 0.7 else "LOW"
        print(f"ID: {z['cluster_id']}, Score: {z['risk_score']}, Count: {z['report_count']}, Scam: {z['primary_scam_type']} [{status}]")
    
    # 2. Test Solo Female
    print("\n--- Solo Female ---")
    resp = requests.get(url, params={"demographic": "Solo Female"})
    data = resp.json()
    for z in data[:3]:
        print(f"ID: {z['cluster_id']}, Score: {z['risk_score']}, Count: {z['report_count']}, Scam: {z['primary_scam_type']}")

if __name__ == "__main__":
    try:
        test_heatmap()
    except Exception as e:
        print(f"Error: {e}")
