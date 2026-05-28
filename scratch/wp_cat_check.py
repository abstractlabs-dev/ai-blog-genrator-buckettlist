"""Fetch WordPress categories and verify mapping."""
import sys
import base64
import requests
import json

sys.path.insert(0, '/app')

from src.config import Config

base_url = Config.WORDPRESS_BASE_URL.strip().rstrip('/')
username = Config.WORDPRESS_USERNAME.strip()
token = Config.WORDPRESS_TOKEN.replace(' ', '')
auth = base64.b64encode(f'{username}:{token}'.encode()).decode()
headers = {'Authorization': f'Basic {auth}', 'Content-Type': 'application/json'}

# Get all WP categories
resp = requests.get(f'{base_url}/wp-json/wp/v2/categories?per_page=100', headers=headers, timeout=30)
cats = resp.json()
print(f'Total categories found: {len(cats)}')
print()

for cat in sorted(cats, key=lambda c: c.get('id', 0)):
    cat_id = cat.get('id', 0)
    parent_id = cat.get('parent', 0)
    cat_name = cat.get('name', '')
    print(f'  ID={cat_id:4d}  parent={parent_id:4d}  name={cat_name}')

# Now check what categories_mapping.json maps to
mapping = Config.CATEGORIES_MAPPING
print()
print('=== categories_mapping.json values ===')
print('Parents:', mapping.get('parents', {}))
print()

real_cat_ids = {c.get('id') for c in cats}
print('=== Checking for ID=1 (placeholder) issues ===')
for section_name in ['product_categories', 'industry_categories']:
    section = mapping.get(section_name, {})
    for name, cid in section.items():
        status = 'OK' if cid in real_cat_ids else 'MISSING from WP'
        print(f"  [{status}] '{name}' -> ID {cid}")
