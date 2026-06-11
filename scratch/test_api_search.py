import requests
import json
import sys

def main():
    url = "http://localhost:5000/api/search"
    headers = {"Content-Type": "application/json"}
    
    # We test with the 3 pre-populated fallback videos
    video_ids = ["WAN704dCy-g", "M2j7tx0Pju8", "JsQHC_2I4gw"]
    
    # Test query 1: "ความศรัทธา"
    data1 = {
        "video_ids": video_ids,
        "query": "ความศรัทธา",
        "threshold": 80.0,
        "channel_name": "@AssabiqoonPublisher"
    }
    
    print("Sending search request for 'ความศรัทธา'...")
    try:
        r = requests.post(url, headers=headers, json=data1, timeout=5)
        print(f"Status Code: {r.status_code}")
        print("Response:")
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Request failed: {e}")
        
    print("\n" + "="*50 + "\n")
    
    # Test query 2: "น้ำละหมาด" (Testing synonyms expansion)
    data2 = {
        "video_ids": video_ids,
        "query": "น้ำละหมาด",
        "threshold": 80.0,
        "channel_name": "@AssabiqoonPublisher"
    }
    
    print("Sending search request for 'น้ำละหมาด' (synonyms test)...")
    try:
        r = requests.post(url, headers=headers, json=data2, timeout=5)
        print(f"Status Code: {r.status_code}")
        print("Response:")
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    main()
