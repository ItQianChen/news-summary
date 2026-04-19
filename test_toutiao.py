import requests
import json

url = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*"
}
res = requests.get(url, headers=headers)
with open("test_toutiao_hot.json", "w", encoding="utf-8") as f:
    json.dump(res.json(), f, ensure_ascii=False, indent=2)
print("Saved to test_toutiao_hot.json")
