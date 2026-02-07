#!/usr/bin/env python3
"""
Helper script to generate a list of no-rent item IDs from the TAKP database.
This script queries the items table for items where norent = 0.

Usage:
    python generate_no_rent_list.py [database_connection_string]
    
Or set environment variables:
    DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
    
Or modify the connection settings in this script.

Output: no_rent_items.json (list of item IDs)
"""

import json
import os
import sys

try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False
    print("Warning: pymysql not installed. Install with: pip install pymysql")
    print("You can also manually create no_rent_items.json with a list of item IDs.")

def query_no_rent_items(host='localhost', user='eq', password='eq', database='peq', port=3306):
    """Query database for no-rent items (norent = 0)."""
    if not HAS_PYMYSQL:
        return None
    
    try:
        connection = pymysql.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port,
            cursorclass=pymysql.cursors.DictCursor
        )
        
        with connection.cursor() as cursor:
            # Query for items where norent = 0 (no-rent items)
            sql = "SELECT id FROM items WHERE norent = 0"
            cursor.execute(sql)
            results = cursor.fetchall()
            
            # Extract item IDs
            item_ids = [row['id'] for row in results]
            return item_ids
            
    except Exception as e:
        print(f"Error querying database: {e}")
        return None
    finally:
        if 'connection' in locals():
            connection.close()

def load_from_file(filepath):
    """Load no-rent item IDs from a text file (one ID per line)."""
    item_ids = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and line.isdigit():
                    item_ids.append(int(line))
        return item_ids
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
        return None

def main():
    """Generate no_rent_items.json from database or file."""
    output_file = "no_rent_items.json"
    
    # Try to get connection info from environment or command line
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_user = os.environ.get('DB_USER', 'eq')
    db_password = os.environ.get('DB_PASSWORD', 'eq')
    db_name = os.environ.get('DB_NAME', 'peq')
    db_port = int(os.environ.get('DB_PORT', '3306'))
    
    # Check for command line argument (connection string or file path)
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        # If it's a file path, try to load from file
        if os.path.exists(arg):
            print(f"Loading no-rent items from file: {arg}")
            item_ids = load_from_file(arg)
            if item_ids:
                with open(output_file, 'w') as f:
                    json.dump(item_ids, f, indent=2)
                print(f"✓ Generated {output_file} with {len(item_ids)} no-rent items")
                return
        else:
            print(f"File not found: {arg}")
    
    # Try to query database
    if HAS_PYMYSQL:
        print(f"Querying database {db_name}@{db_host}...")
        item_ids = query_no_rent_items(db_host, db_user, db_password, db_name, db_port)
        
        if item_ids:
            with open(output_file, 'w') as f:
                json.dump(item_ids, f, indent=2)
            print(f"✓ Generated {output_file} with {len(item_ids)} no-rent items")
            return
    
    # Fallback: create empty list or provide instructions
    print("\nCould not generate no-rent items list automatically.")
    print("\nOptions:")
    print("1. Install pymysql and configure database connection:")
    print("   pip install pymysql")
    print("   export DB_HOST=localhost DB_USER=eq DB_PASSWORD=eq DB_NAME=peq")
    print("   python generate_no_rent_list.py")
    print("\n2. Export from database manually:")
    print("   mysql -u eq -p peq -e 'SELECT id FROM items WHERE norent = 0' > no_rent_items.txt")
    print("   python generate_no_rent_list.py no_rent_items.txt")
    print("\n3. Create no_rent_items.json manually with a JSON array of item IDs:")
    print('   [123, 456, 789, ...]')
    
    # Create empty file as placeholder
    with open(output_file, 'w') as f:
        json.dump([], f, indent=2)
    print(f"\nCreated empty {output_file}. Update it with no-rent item IDs.")

if __name__ == "__main__":
    main()
