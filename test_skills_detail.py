import requests, json

r = requests.get('http://127.0.0.1:5000/api/skills')
data = r.json()
for s in data['skills']:
    print(json.dumps(s, indent=2, ensure_ascii=False))
    print('---')
