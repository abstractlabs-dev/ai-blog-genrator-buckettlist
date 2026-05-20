import csv, json, sys

with open('/app/data/database/articles.csv', 'r', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

print(f'Total articles in DB: {len(rows)}')
for r in rows:
    url = r.get('wp_published_url', '') or ''
    short_url = url[-55:] if url else '(none)'
    print(f"  [{r.get('id','?')}] {r.get('title','?')[:55]:<55} | Published: {r.get('published','?')} | {short_url}")

with open('/app/data/database/stats.json', 'r') as f:
    stats = json.load(f)
print(f"\nStats: {json.dumps(stats, indent=2)}")
