#!/usr/bin/env python3
import requests, json, time

while True:
    try:
        r = requests.get("http://localhost:8099/health", timeout=2)
        data = r.json()
        
        # Show ALL tracks (not just stable ones)
        if data.get("objects"):
            print(f"\n=== {time.strftime('%H:%M:%S')} ===")
            for obj in data["objects"]:
                print(f"  ID#{obj['id']}: {obj['class']} (box: {obj['box']})")
        
        # Show delivery flags
        delivery = data.get("delivery", {})
        active = [k for k,v in delivery.items() if v]
        if active:
            print(f"  ACTIVE: {active}")
            
    except Exception as e:
        print(f"Error: {e}")
    
    time.sleep(0.5)
