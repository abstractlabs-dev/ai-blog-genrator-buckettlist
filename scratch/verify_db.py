import os
import shutil
import csv
import json
import sys

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.utils import CSVManager
from src.stats_manager import StatsManager

def verify():
    db_dir = os.path.join("data", "database")
    csv_path = os.path.join(db_dir, "articles.csv")
    stats_path = os.path.join(db_dir, "stats.json")
    
    print("=== STARTING VERIFICATION ===")
    
    # 1. Check existing files exist
    if not os.path.exists(csv_path):
        print(f"ERROR: {csv_path} does not exist!")
        return
    if not os.path.exists(stats_path):
        print(f"ERROR: {stats_path} does not exist!")
        return

    # Count rows before migration
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers_before = next(reader)
        rows_before = list(reader)
    
    print(f"Original CSV row count: {len(rows_before)}")
    print(f"Original CSV headers: {headers_before}")

    # Read stats before migration
    with open(stats_path, 'r', encoding='utf-8') as f:
        stats_before = json.load(f)
    print(f"Original Stats: {json.dumps(stats_before, indent=2)}")

    # 2. Make backups
    csv_backup = csv_path + ".bak"
    stats_backup = stats_path + ".bak"
    shutil.copy(csv_path, csv_backup)
    shutil.copy(stats_path, stats_backup)
    print("Created backups of articles.csv and stats.json.")

    try:
        # 3. Instantiate CSVManager to trigger automatic header migration
        print("\nInstantiating CSVManager...")
        manager = CSVManager()
        
        # Verify CSV after migration
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers_after = next(reader)
            rows_after = list(reader)
            
        print(f"New CSV row count: {len(rows_after)}")
        print(f"New CSV headers: {headers_after}")
        
        # Assertions
        assert len(rows_before) == len(rows_after), f"Row count mismatch! Before: {len(rows_before)}, After: {len(rows_after)}"
        print("SUCCESS: Row counts match perfectly!")
        
        # Assert that the data inside rows remains completely identical for common fields
        for idx, (row_b, row_a) in enumerate(zip(rows_before, rows_after)):
            # Convert row_b to a dict mapping headers_before to values
            dict_b = dict(zip(headers_before, row_b))
            dict_a = dict(zip(headers_after, row_a))
            for h in headers_before:
                assert dict_b[h] == dict_a[h], f"Value mismatch in row {idx} for column '{h}': '{dict_b[h]}' vs '{dict_a[h]}'"
        print("SUCCESS: Existing row values are 100% identical!")

        # 4. Instantiate and check StatsManager
        print("\nLoading stats via StatsManager...")
        stats_after = StatsManager.get_stats()
        print(f"Loaded Stats: {json.dumps(stats_after, indent=2)}")
        
        # Assert that the wordpress count remains 150
        assert stats_after["published"]["wordpress"] == 150, "WordPress stats got modified!"
        assert stats_after["published"]["linkedin"] == 0, "linkedin stats not initialized to 0!"
        assert stats_after["published"]["medium"] == 0, "medium stats not initialized to 0!"
        print("SUCCESS: StatsManager initialized successfully, preserving existing values and adding new platforms!")
        
        print("\n=== VERIFICATION PASSED SUCCESSFULLY ===")
    except Exception as e:
        print(f"\nFAILURE: {e}")
        # Restore backups
        shutil.copy(csv_backup, csv_path)
        shutil.copy(stats_backup, stats_path)
        print("Restored original files from backup.")
    finally:
        # Remove backups so we don't leave clutter
        if os.path.exists(csv_backup):
            os.remove(csv_backup)
        if os.path.exists(stats_backup):
            os.remove(stats_backup)

if __name__ == "__main__":
    verify()
