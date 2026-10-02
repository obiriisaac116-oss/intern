import json, os

# Remove stale db so tests start clean
db = os.path.join(os.path.dirname(__file__), "tracker.db")
if os.path.exists(db):
    os.remove(db)

import app as appmod

appmod.init_db()
client = appmod.app.test_client()

# 1. Create two people
r = client.post('/api/personnel',
    json={'name':'Maria Santos','institution':'UP Manila','phone':'09171234567'})
assert r.status_code == 201, r.data
p1 = json.loads(r.data)
print('Created:', p1['name'])

r = client.post('/api/personnel',
    json={'name':'Juan dela Cruz','institution':'DLSU','phone':'09281234567'})
assert r.status_code == 201, r.data
p2 = json.loads(r.data)
print('Created:', p2['name'])

# 2. Add 2 visits for Maria
r = client.post(f'/api/personnel/{p1["id"]}/visits',
    json={'start_date':'2026-01-10','end_date':'2026-01-24',
          'department':'Cardiology','notes':'First rotation'})
assert r.status_code == 201, r.data

r = client.post(f'/api/personnel/{p1["id"]}/visits',
    json={'start_date':'2026-06-01','department':'Radiology'})
assert r.status_code == 201, r.data
print('Added 2 visits for Maria')

# 3. Check-in lookup
r = client.get('/api/checkin?q=maria')
data = json.loads(r.data)
assert len(data) == 1
msg = data[0]['visit_message']
print('Check-in message for Maria:', msg)
assert data[0]['visit_count'] == 2
assert msg == '3rd time here', f"Expected '3rd time here', got '{msg}'"

# 4. Juan first-time
r = client.get('/api/checkin?q=juan')
data = json.loads(r.data)
assert data[0]['visit_message'] == 'First time here!', data[0]['visit_message']
print('Check-in message for Juan:', data[0]['visit_message'])

# 5. List all personnel
r = client.get('/api/personnel')
people = json.loads(r.data)
assert len(people) == 2
print('Personnel count:', len(people))

# 6. Validation – missing fields
r = client.post('/api/personnel', json={'name':'', 'institution':'X', 'phone':'123'})
assert r.status_code == 400

# 7. Edit personnel
r = client.put(f'/api/personnel/{p1["id"]}',
    json={'name':'Maria R. Santos','institution':'UP Manila','phone':'09171234567'})
assert r.status_code == 200
updated = json.loads(r.data)
assert updated['name'] == 'Maria R. Santos'
print('Updated name:', updated['name'])

# 8. Delete visit
r = client.get(f'/api/personnel/{p1["id"]}/visits')
visits = json.loads(r.data)
r = client.delete(f'/api/visits/{visits[0]["id"]}')
assert r.status_code == 200

r = client.get(f'/api/personnel/{p1["id"]}')
p = json.loads(r.data)
assert p['visit_count'] == 1
print('Visit count after delete:', p['visit_count'])

print()
print('ALL TESTS PASSED')
