import requests, time

sid = '117cc0c53a5e'
for i in range(90):
    r = requests.get(f'http://127.0.0.1:5000/api/sessions/{sid}/status')
    st = r.json()['status']
    print(f'[{i*5}s] {st}')
    if st in ('done', 'error', 'stopping'):
        break
    time.sleep(5)

# Check skills
r = requests.get('http://127.0.0.1:5000/api/skills')
data = r.json()
print(f'\nSkills: {len(data["skills"])}')
for s in data['skills']:
    print(f'  [{s["action_type"]}] {s["description"][:80]}')
