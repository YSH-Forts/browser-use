import requests, time

# Clear old skills first
r = requests.get('http://127.0.0.1:5000/api/skills')
old = r.json().get('skills', [])
print(f'Old skills: {len(old)}')
for s in old:
    requests.delete(f'http://127.0.0.1:5000/api/skills/{s["id"]}')

# Create session
r = requests.post('http://127.0.0.1:5000/api/sessions')
sid = r.json()['session_id']
print('Session:', sid)

task = """1. Navigate to https://www.capitaliq.com/CIQDotNet/my/dashboard.aspx
2. Wait 5 seconds for the Okta login page to fully load
3. Click the LOG IN link/button if the email field is not visible
4. Enter the email/username field with: meijun.sun@bowayalloy.com
5. Click the Next or Continue button
6. Wait 5 seconds for the password page to load
7. Enter the password field with: Bowayalloy$2025
8. Click the Sign In button
9. Wait 10 seconds for the page to process login
10. Report the current URL and page title"""

r = requests.post(f'http://127.0.0.1:5000/api/sessions/{sid}/execute', json={'task': task})
print('Execute:', r.status_code)
print('Task started...')
