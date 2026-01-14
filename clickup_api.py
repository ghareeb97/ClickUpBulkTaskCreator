import requests

BASE_URL = "https://api.clickup.com/api/v2"


def get_headers(api_token):
    return {
        "Authorization": api_token,
        "Content-Type": "application/json"
    }


def get_custom_fields(list_id, api_token):
    """Fetch custom fields for a ClickUp list."""
    url = f"{BASE_URL}/list/{list_id}/field"
    response = requests.get(url, headers=get_headers(api_token))

    if response.status_code != 200:
        raise Exception(f"Failed to fetch custom fields: {response.status_code} - {response.text}")

    return response.json().get("fields", [])


def create_task(list_id, name, description, custom_fields, api_token):
    """Create a task in a ClickUp list.

    Args:
        list_id: The ClickUp list ID
        name: Task name
        description: Task description
        custom_fields: List of dicts with 'id' and 'value' keys
        api_token: ClickUp API token

    Returns:
        tuple: (success: bool, message: str)
    """
    url = f"{BASE_URL}/list/{list_id}/task"

    payload = {
        "name": name,
        "description": description or ""
    }

    if custom_fields:
        payload["custom_fields"] = custom_fields

    response = requests.post(url, headers=get_headers(api_token), json=payload)

    if response.status_code in (200, 201):
        return True, "Created successfully"
    else:
        return False, f"{response.status_code} - {response.text[:200]}"


def get_tasks(list_id, api_token):
    """Fetch all tasks from a ClickUp list."""
    url = f"{BASE_URL}/list/{list_id}/task"
    response = requests.get(url, headers=get_headers(api_token))

    if response.status_code != 200:
        raise Exception(f"Failed to fetch tasks: {response.status_code} - {response.text}")

    return response.json().get("tasks", [])


def delete_task(task_id, api_token):
    """Delete a task from ClickUp.

    Returns:
        tuple: (success: bool, message: str)
    """
    url = f"{BASE_URL}/task/{task_id}"
    response = requests.delete(url, headers=get_headers(api_token))

    if response.status_code in (200, 204):
        return True, "Deleted successfully"
    else:
        return False, f"{response.status_code} - {response.text[:200]}"


def add_dropdown_option(field_id, option_name, api_token):
    """Add a new option to a dropdown custom field.

    Args:
        field_id: The custom field ID
        option_name: Name for the new option
        api_token: ClickUp API token

    Returns:
        tuple: (success: bool, option_id or error_message: str)
    """
    url = f"{BASE_URL}/field/{field_id}/option"

    payload = {
        "name": option_name
    }

    response = requests.post(url, headers=get_headers(api_token), json=payload)

    if response.status_code in (200, 201):
        option_data = response.json()
        return True, option_data.get("id")
    else:
        return False, f"{response.status_code} - {response.text[:200]}"


def link_tasks(task_id, links_to_id, api_token):
    """Link two tasks together as related tasks.

    Args:
        task_id: The task ID to add link from
        links_to_id: The task ID to link to
        api_token: ClickUp API token

    Returns:
        tuple: (success: bool, message: str)
    """
    url = f"{BASE_URL}/task/{task_id}/link/{links_to_id}"

    response = requests.post(url, headers=get_headers(api_token))

    if response.status_code in (200, 201):
        return True, "Linked successfully"
    else:
        return False, f"{response.status_code} - {response.text[:200]}"
