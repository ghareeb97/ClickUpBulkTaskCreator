import streamlit as st
import json
from clickup_api import get_custom_fields, create_task, link_tasks
from excel_parser import get_sheet_names, parse_excel_workbook

# Load config defaults
try:
    with open("config.json", "r") as f:
        config = json.load(f)
except FileNotFoundError:
    config = {"default_custom_fields": {}, "required_custom_fields": []}

def check_required_fields(actual_fields, required_fields):
    """Check which required fields exist and which are missing."""
    actual_by_name = {f.get("name"): f for f in actual_fields}
    results = []

    for req in required_fields:
        name = req.get("name")
        req_type = req.get("type")
        actual = actual_by_name.get(name)

        if actual and actual.get("type") == req_type:
            # Field exists with correct type
            # Check required options for dropdowns
            missing_options = []
            if req_type == "drop_down" and req.get("required_options"):
                actual_options = [opt.get("name") for opt in actual.get("type_config", {}).get("options", [])]
                missing_options = [opt for opt in req.get("required_options") if opt not in actual_options]

            results.append({
                "name": name,
                "exists": True,
                "field": actual,
                "missing_options": missing_options,
                "instructions": req.get("instructions", [])
            })
        else:
            results.append({
                "name": name,
                "exists": False,
                "expected_type": req_type,
                "instructions": req.get("instructions", [])
            })

    return results

st.set_page_config(page_title="ClickUp Bulk Task Creator", page_icon="✅", layout="wide")
st.title("ClickUp Bulk Task Creator")

# Sidebar - Configuration
with st.sidebar:
    st.header("Configuration")

    # API Token - try secrets first, then allow manual entry
    default_token = ""
    try:
        default_token = st.secrets.get("API_TOKEN", "")
    except Exception:
        pass

    api_token = st.text_input(
        "API Token",
        value=default_token,
        type="password",
        help="Your ClickUp API token"
    )

    list_id = st.text_input(
        "List ID",
        help="The ClickUp List ID where tasks will be created"
    )

    if api_token and list_id:
        if st.button("Check Fields", type="primary"):
            try:
                fields = get_custom_fields(list_id, api_token)
                st.session_state["custom_fields"] = fields

                # Check required fields
                required = config.get("required_custom_fields", [])
                if required:
                    field_status = check_required_fields(fields, required)
                    st.session_state["field_status"] = field_status

                # Validate Epic options against required epics from Excel
                required_epics = st.session_state.get("required_epics", set())
                if required_epics:
                    # Find Epic field
                    epic_field = next((f for f in fields if f.get("name") == "Epic" and f.get("type") == "drop_down"), None)
                    if epic_field:
                        existing_options = {opt.get("name") for opt in epic_field.get("type_config", {}).get("options", [])}
                        missing_epics = required_epics - existing_options
                        st.session_state["missing_epics"] = missing_epics
                    else:
                        # Epic field doesn't exist - all epics are "missing"
                        st.session_state["missing_epics"] = required_epics
                else:
                    st.session_state["missing_epics"] = set()

                st.success(f"Loaded {len(fields)} custom fields")
            except Exception as e:
                st.error(f"Error: {e}")

        # Show Setup Status
        if "field_status" in st.session_state:
            st.markdown("---")
            st.subheader("Setup Status")

            field_status = st.session_state["field_status"]
            missing_epics = st.session_state.get("missing_epics", set())

            fields_ready = all(f["exists"] and not f.get("missing_options") for f in field_status)
            epics_ready = len(missing_epics) == 0
            all_ready = fields_ready and epics_ready

            if all_ready:
                st.success("All required fields are configured!")
                st.session_state["setup_complete"] = True
            else:
                st.session_state["setup_complete"] = False

            for field in field_status:
                if field["exists"] and not field.get("missing_options"):
                    st.markdown(f"✅ **{field['name']}** - Ready")
                elif field["exists"] and field.get("missing_options"):
                    st.markdown(f"⚠️ **{field['name']}** - Missing options")
                    with st.expander(f"Add missing options to {field['name']}"):
                        st.write(f"Missing: {', '.join(field['missing_options'])}")
                        st.write("Add these options in ClickUp, then click 'Check Fields' again.")
                else:
                    st.markdown(f"❌ **{field['name']}** - Not found")
                    with st.expander(f"How to create {field['name']}"):
                        for step in field.get("instructions", []):
                            st.markdown(step)

            # Show missing Epic options from Excel
            if missing_epics:
                st.markdown(f"❌ **Epic Options** - {len(missing_epics)} missing")
                with st.expander("Create these Epic options in ClickUp"):
                    st.write("The following Epic values from your Excel file don't exist in ClickUp:")
                    for epic in sorted(missing_epics):
                        st.code(epic, language=None)
                    st.markdown("---")
                    st.markdown("**How to add them:**")
                    st.markdown("1. Open your ClickUp List")
                    st.markdown("2. Find the **Epic** column")
                    st.markdown("3. Click on any cell in that column")
                    st.markdown("4. Click **+ Add Option**")
                    st.markdown("5. Paste each Epic name **exactly** as shown above")
                    st.markdown("6. Click **'Check Fields'** again to verify")
            elif st.session_state.get("required_epics"):
                st.markdown("✅ **Epic Options** - All values exist")

# Main area
col1, col2 = st.columns([1, 1])

with col1:
    st.header("Task Input")

    input_method = st.radio("Input method", ["Upload JSON", "Paste JSON", "Upload Excel"])

    tasks = []

    if input_method == "Upload JSON":
        uploaded_file = st.file_uploader("Upload JSON file", type=["json"])
        if uploaded_file:
            try:
                tasks = json.load(uploaded_file)
                st.success(f"Loaded {len(tasks)} tasks")
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}")

    elif input_method == "Paste JSON":
        json_text = st.text_area(
            "Paste JSON",
            height=300,
            placeholder='[{"name": "Task 1", "description": "Description 1"}, ...]'
        )
        if json_text:
            try:
                tasks = json.loads(json_text)
                st.success(f"Parsed {len(tasks)} tasks")
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}")

    elif input_method == "Upload Excel":
        uploaded_file = st.file_uploader(
            "Upload Excel file",
            type=["xlsx", "xls"],
            help="Upload HNDL User Stories format Excel file"
        )

        if uploaded_file:
            try:
                # Store file bytes for reprocessing when sheet selection changes
                file_bytes = uploaded_file.read()

                # Get available sheets
                sheet_names = get_sheet_names(file_bytes)

                # Separate Epics sheet from User Story sheets
                epics_sheet = "Epics" if "Epics" in sheet_names else None
                user_story_sheets = [s for s in sheet_names if s != "Epics" and s != "User story status"]

                if epics_sheet:
                    st.success("Found Epics sheet with epic definitions")
                else:
                    st.warning("No 'Epics' sheet found - Epic field will not be populated")

                # Multi-select for sheets to import
                st.subheader("Select Sheets to Import")
                selected_sheets = st.multiselect(
                    "User Story Sheets",
                    options=user_story_sheets,
                    default=user_story_sheets,
                    help="Select which sheets to import as tasks"
                )

                if selected_sheets:
                    # Parse selected sheets
                    tasks, stats = parse_excel_workbook(file_bytes, selected_sheets)

                    # Extract unique Epic names from parsed tasks for validation
                    unique_epics = set(t.get("epic") for t in tasks if t.get("epic"))

                    # Check if required epics changed - invalidate previous validation
                    prev_required = st.session_state.get("required_epics", set())
                    if unique_epics != prev_required:
                        st.session_state["required_epics"] = unique_epics
                        # Clear validation state to force re-check
                        st.session_state["missing_epics"] = unique_epics  # Assume all missing until checked
                        st.session_state["setup_complete"] = False

                    st.success(
                        f"Loaded {stats['total_tasks']} tasks from {stats['sheets_processed']} sheets. "
                        f"{stats['with_epic']} tasks linked to Epics."
                    )

                    if unique_epics:
                        st.warning(f"Found {len(unique_epics)} unique Epic(s) - click **'Check Fields'** to validate they exist in ClickUp")

            except Exception as e:
                st.error(f"Error parsing Excel: {e}")
                import traceback
                st.code(traceback.format_exc())

    # Tasks Preview
    if tasks:
        st.subheader("Tasks Preview")

        for i, task in enumerate(tasks[:10]):
            task_name = task.get('name', 'Unnamed')
            epic = task.get('epic')

            if epic:
                st.text(f"{i+1}. {task_name} [Epic: {epic}]")
            else:
                st.text(f"{i+1}. {task_name}")

        if len(tasks) > 10:
            st.text(f"... and {len(tasks) - 10} more")

        # Expandable full preview
        with st.expander("View All Tasks"):
            for i, task in enumerate(tasks):
                st.markdown(f"**{i+1}. {task.get('name', 'Unnamed')}**")
                if task.get('epic'):
                    st.caption(f"Epic: {task.get('epic')}")
                desc = task.get('description', '')
                if desc:
                    preview = desc[:200] + "..." if len(desc) > 200 else desc
                    st.text(preview)
                st.divider()

with col2:
    st.header("Custom Fields")

    custom_field_values = {}
    epic_field_info = None

    if "custom_fields" in st.session_state and st.session_state["custom_fields"]:
        fields = st.session_state["custom_fields"]

        for field in fields:
            field_name = field.get("name", "Unknown")
            field_id = field.get("id")
            field_type = field.get("type")

            # Check if there's a config default
            default_value = config.get("default_custom_fields", {}).get(field_name)

            # Special handling for Epic field when using Excel import
            if field_name == "Epic" and field_type == "drop_down" and input_method == "Upload Excel":
                st.info(f"'{field_name}' will be auto-populated from Excel Epics sheet")

                # Store Epic field info for task creation
                options = field.get("type_config", {}).get("options", [])
                epic_field_info = {
                    "id": field_id,
                    "options": {opt.get("name"): opt.get("id") for opt in options}
                }
                st.session_state["epic_field_info"] = epic_field_info

                # Show available Epic options for reference
                with st.expander("Available Epic Options in ClickUp"):
                    for opt in options:
                        st.text(f"- {opt.get('name')}")
                continue

            # Enable checkbox
            enabled = st.checkbox(
                f"Set '{field_name}'",
                value=default_value is not None,
                key=f"enable_{field_id}"
            )

            if enabled:
                if field_type == "drop_down":
                    options = field.get("type_config", {}).get("options", [])
                    option_names = [opt.get("name") for opt in options]

                    # Find default index
                    default_idx = 0
                    if default_value and default_value in option_names:
                        default_idx = option_names.index(default_value)

                    selected = st.selectbox(
                        field_name,
                        options=option_names,
                        index=default_idx,
                        key=f"value_{field_id}"
                    )

                    # Find the option ID for the selected value
                    for opt in options:
                        if opt.get("name") == selected:
                            custom_field_values[field_id] = opt.get("id")
                            break

                elif field_type == "text":
                    value = st.text_input(
                        field_name,
                        value=default_value or "",
                        key=f"value_{field_id}"
                    )
                    if value:
                        custom_field_values[field_id] = value

                elif field_type == "number":
                    value = st.number_input(
                        field_name,
                        value=float(default_value) if default_value else 0.0,
                        key=f"value_{field_id}"
                    )
                    custom_field_values[field_id] = value

                elif field_type == "checkbox":
                    value = st.checkbox(
                        f"{field_name} value",
                        value=bool(default_value),
                        key=f"value_{field_id}"
                    )
                    custom_field_values[field_id] = value

                else:
                    st.info(f"Field type '{field_type}' - enter value manually")
                    value = st.text_input(
                        field_name,
                        value=str(default_value) if default_value else "",
                        key=f"value_{field_id}"
                    )
                    if value:
                        custom_field_values[field_id] = value
    else:
        st.info("Enter List ID and click 'Load Custom Fields' to see available fields")

# Create Tasks Section
st.markdown("---")
st.header("Create Tasks")

if custom_field_values:
    st.write("**Custom fields to apply:**")
    for field_id, value in custom_field_values.items():
        # Find field name
        if "custom_fields" in st.session_state:
            for f in st.session_state["custom_fields"]:
                if f.get("id") == field_id:
                    st.write(f"- {f.get('name')}: {value}")
                    break

if tasks and api_token and list_id:
    # Check if setup is complete
    setup_complete = st.session_state.get("setup_complete", False)
    fields_checked = "field_status" in st.session_state

    if not fields_checked:
        st.warning("Click **'Check Fields'** in the sidebar first to verify custom fields are set up.")
    elif not setup_complete:
        st.error("Some required custom fields are missing. See **Setup Status** in the sidebar for instructions.")

    # Option to link related tasks (only for Excel imports with Epics)
    has_epics = any(t.get("epic") for t in tasks)
    link_related = False
    if has_epics and input_method == "Upload Excel":
        link_related = st.checkbox(
            "Link related user stories within same Epic",
            value=True,
            help="Creates 'related to' links between all user stories that share the same Epic"
        )

    # Only enable Create Tasks if setup is complete (or no required fields defined)
    # Also check that all Epic options exist
    no_required_fields = not config.get("required_custom_fields")
    missing_epics = st.session_state.get("missing_epics", set())
    can_create = (setup_complete or no_required_fields) and len(missing_epics) == 0

    # Show warning if Epic options are missing
    if missing_epics:
        st.error(f"{len(missing_epics)} Epic option(s) missing in ClickUp. See **Setup Status** in sidebar.")

    if st.button("Create Tasks", type="primary", disabled=not can_create):
        # Get Epic field info if available
        epic_field_info = st.session_state.get("epic_field_info")

        progress = st.progress(0)
        status = st.empty()
        results = {"success": 0, "failed": 0, "links_created": 0}

        # Track created task IDs by Epic for linking
        epic_task_ids = {}  # epic_name -> [task_id1, task_id2, ...]

        # Create all tasks
        total_steps = len(tasks)
        if link_related:
            # We'll need additional steps for linking
            total_steps = len(tasks)  # Progress will reset for linking phase

        for i, task in enumerate(tasks):
            task_name = task.get("name", "Unnamed")
            task_desc = task.get("description", "")
            task_epic = task.get("epic")

            # Build custom fields list for this specific task
            cf_list = [{"id": fid, "value": val} for fid, val in custom_field_values.items()]

            # Add Epic custom field if applicable
            if task_epic and epic_field_info:
                epic_option_id = epic_field_info["options"].get(task_epic)
                if epic_option_id:
                    cf_list.append({"id": epic_field_info["id"], "value": epic_option_id})

            success, msg = create_task(list_id, task_name, task_desc, cf_list, api_token)

            if success:
                results["success"] += 1
                status.text(f"Created: {task_name}")

                # Extract task ID from response for linking
                if link_related and task_epic:
                    # The create_task function returns (True, "Created successfully")
                    # We need to modify it to return the task ID, or fetch tasks after
                    # For now, we'll track by name and fetch IDs after
                    if task_epic not in epic_task_ids:
                        epic_task_ids[task_epic] = []
                    epic_task_ids[task_epic].append(task_name)
            else:
                results["failed"] += 1
                status.text(f"Failed: {task_name} - {msg}")

            progress.progress((i + 1) / len(tasks))

        # Phase 2: Link related tasks within each Epic
        if link_related and epic_task_ids:
            status.text("Linking related tasks...")
            from clickup_api import get_tasks

            # Fetch all created tasks to get their IDs
            try:
                all_tasks_in_list = get_tasks(list_id, api_token)
                task_name_to_id = {t["name"]: t["id"] for t in all_tasks_in_list}

                # Link tasks within each Epic
                for epic_name, task_names in epic_task_ids.items():
                    task_ids = [task_name_to_id.get(name) for name in task_names]
                    task_ids = [tid for tid in task_ids if tid]  # Filter out None

                    if len(task_ids) >= 2:
                        # Link each task to the next one (chain)
                        for j in range(len(task_ids) - 1):
                            success, _ = link_tasks(task_ids[j], task_ids[j + 1], api_token)
                            if success:
                                results["links_created"] += 1

                status.text("Linking complete!")
            except Exception as e:
                status.text(f"Error linking tasks: {e}")

        # Show results summary
        summary = f"Done! Created: {results['success']}, Failed: {results['failed']}"
        if results["links_created"]:
            summary += f", Links: {results['links_created']}"
        st.success(summary)
else:
    missing = []
    if not tasks:
        missing.append("tasks")
    if not api_token:
        missing.append("API token")
    if not list_id:
        missing.append("List ID")
    st.warning(f"Please provide: {', '.join(missing)}")
