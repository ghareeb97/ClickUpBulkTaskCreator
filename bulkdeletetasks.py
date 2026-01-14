import requests
import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bulk deletion script: retrieves all tasks from a ClickUp list and deletes them.
# WARNING: This is a destructive operation and cannot be undone!

# Parse command-line arguments
if len(sys.argv) < 2:
    print("Usage: py bulkdeletetasks.py <LIST_ID>")
    print("\nExample:")
    print("  py bulkdeletetasks.py 123456789")
    print("\nNote: API_TOKEN must be set in .env file")
    print("\nWARNING: This will delete ALL tasks in the list!")
    sys.exit(1)

LIST_ID = sys.argv[1]

API_TOKEN = os.environ.get("API_TOKEN")

if not API_TOKEN:
    raise ValueError("API_TOKEN must be set in .env file")

if not LIST_ID:
    raise ValueError("LIST_ID must be provided as first argument")

# API endpoints
GET_TASKS_URL = f"https://api.clickup.com/api/v2/list/{LIST_ID}/task"
DELETE_TASK_URL = "https://api.clickup.com/api/v2/task/{task_id}"

headers = {
    "Authorization": API_TOKEN,
    "Content-Type": "application/json"
}

# Confirm deletion
print(f"WARNING: You are about to delete ALL tasks in List ID: {LIST_ID}")
confirmation = input("Type 'DELETE' to confirm: ")

if confirmation != "DELETE":
    print("Deletion cancelled.")
    sys.exit(0)

print(f"\nFetching tasks from List ID: {LIST_ID}...\n")

# Get all tasks from the list
response = requests.get(GET_TASKS_URL, headers=headers)

if response.status_code != 200:
    print(f"✗ Failed to fetch tasks: {response.status_code} - {response.text[:200]}")
    sys.exit(1)

tasks = response.json().get("tasks", [])

if not tasks:
    print("No tasks found in this list.")
    sys.exit(0)

print(f"Found {len(tasks)} task(s) to delete.\n")

deleted_count = 0
failed_count = 0

for task in tasks:
    task_id = task.get("id")
    task_name = task.get("name")

    delete_url = f"https://api.clickup.com/api/v2/task/{task_id}"
    response = requests.delete(delete_url, headers=headers)

    if response.status_code in (200, 204):
        print(f"✓ Deleted: {task_name}")
        deleted_count += 1
    else:
        print(f"✗ Failed to delete: {task_name} - {response.status_code} - {response.text[:200]}")
        failed_count += 1

print(f"\n{'='*60}")
print(f"Task deletion completed!")
print(f"Total tasks deleted: {deleted_count}")
print(f"Total tasks failed: {failed_count}")
print(f"{'='*60}")
