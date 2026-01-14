import json
import requests
import os
import sys
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

# Simple bulk creation script: loads tasks from JSON and posts them to ClickUp.
# NOTE: Running this will create all tasks each time (no de-duplication).

# Parse command-line arguments
if len(sys.argv) < 3:
    print("Usage: py bulkcreatetasks.py <LIST_ID> <JSON_FILE_PATH>")
    print("\nExample:")
    print("  py bulkcreatetasks.py 123456789 inspection_tasks.json")
    print("\nNote: API_TOKEN must be set in .env file")
    sys.exit(1)

LIST_ID = sys.argv[1]
JSON_FILE_PATH = sys.argv[2]

API_TOKEN = os.environ.get("API_TOKEN")

if not API_TOKEN:
    raise ValueError("API_TOKEN must be set in .env file")

if not LIST_ID:
    raise ValueError("LIST_ID must be provided as first argument")

# Verify JSON file exists
json_path = Path(JSON_FILE_PATH)
if not json_path.exists():
    raise FileNotFoundError(f"JSON file not found: {JSON_FILE_PATH}")

URL = f"https://api.clickup.com/api/v2/list/{LIST_ID}/task"

headers = {
    "Authorization": API_TOKEN,
    "Content-Type": "application/json"
}

# Fetch custom fields to get the "Source" field ID and "Internal" option ID
print(f"Fetching custom fields for list {LIST_ID}...")
fields_url = f"https://api.clickup.com/api/v2/list/{LIST_ID}/field"
fields_response = requests.get(fields_url, headers=headers)

if fields_response.status_code != 200:
    raise Exception(f"Failed to fetch custom fields: {fields_response.status_code} - {fields_response.text}")

fields_data = fields_response.json()
fields = fields_data.get("fields", [])

# Find the "Source" field and "Internal" option
source_field_id = None
internal_option_id = None

for field in fields:
    if field.get("name") == "Source" and field.get("type") == "drop_down":
        source_field_id = field.get("id")
        options = field.get("type_config", {}).get("options", [])
        for option in options:
            if option.get("name") == "Internal":
                internal_option_id = option.get("id")
                break
        break

if not source_field_id or not internal_option_id:
    print("WARNING: 'Source' field or 'Internal' option not found. Tasks will be created without this custom field.")
    print(f"Source field ID: {source_field_id}, Internal option ID: {internal_option_id}\n")
else:
    print(f"✓ Found Source field (ID: {source_field_id})")
    print(f"✓ Found Internal option (ID: {internal_option_id})\n")

print(f"Loading tasks from: {JSON_FILE_PATH}")
print(f"Creating tasks in ClickUp List ID: {LIST_ID}\n")

with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
    tasks = json.load(f)

for task in tasks:
    # Build the task payload
    task_payload = {
        "name": task.get("name"),
        "description": task.get("description", "")
    }

    # Add Source custom field if it was found
    if source_field_id and internal_option_id:
        task_payload["custom_fields"] = [
            {
                "id": source_field_id,
                "value": internal_option_id
            }
        ]

    response = requests.post(URL, headers=headers, json=task_payload)
    if response.status_code in (200, 201):
        print(f"✓ Created: {task.get('name')}")
    else:
        print(f"✗ Failed: {task.get('name')} - {response.status_code} - {response.text[:200]}")

print(f"\n{'='*60}")
print(f"Task creation completed!")
print(f"Total tasks processed: {len(tasks)}")
print(f"{'='*60}")

