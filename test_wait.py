import requests, time, json

sid = '9ab96622e222'
for i in range(60):
    r = requests.get(f'http://127.0.0.1:5000/api/sessions/{sid}/status')
    status = r.json()['status']
    print(f'[{i}] Status: {status}')
    if status in ('done', 'error', 'stopping'):
        break
    time.sleep(5)

r = requests.get('http://127.0.0.1:5000/api/skills')
data = r.json()
print(f'\nTotal skills: {len(data["skills"])}')
for s in data['skills']:
    desc = s.get('description', '')
    print(f'  - {s["id"]}: {desc[:80]}')
