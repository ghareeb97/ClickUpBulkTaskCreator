import streamlit as st
import json
import re
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

# ============================================================
# STEP 1: Select Tasks
# ============================================================
st.header("Step 1: Select Tasks")

input_method = st.radio("Input method", ["Upload JSON", "Paste JSON", "Upload Excel"], index=2)

tasks = []

if input_method == "Upload JSON":
    uploaded_file = st.file_uploader("Upload JSON file", type=["json"])
    if uploaded_file:
        try:
            tasks = json.load(uploaded_file)
            if not st.session_state.get("tasks_ready"):
                st.session_state["tasks_ready"] = True
                st.rerun()
            st.success(f"Loaded {len(tasks)} tasks")
        except json.JSONDecodeError as e:
            st.session_state["tasks_ready"] = False
            st.error(f"Invalid JSON: {e}")
    else:
        st.session_state["tasks_ready"] = False

elif input_method == "Paste JSON":
    json_text = st.text_area(
        "Paste JSON",
        height=300,
        placeholder='[{"name": "Task 1", "description": "Description 1"}, ...]'
    )
    if json_text:
        try:
            tasks = json.loads(json_text)
            if not st.session_state.get("tasks_ready"):
                st.session_state["tasks_ready"] = True
                st.rerun()
            st.success(f"Parsed {len(tasks)} tasks")
        except json.JSONDecodeError as e:
            st.session_state["tasks_ready"] = False
            st.error(f"Invalid JSON: {e}")
    else:
        st.session_state["tasks_ready"] = False

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
                default=[],
                help="Select which sheets to import as tasks"
            )

            if selected_sheets:
                # Parse selected sheets
                tasks, stats = parse_excel_workbook(file_bytes, selected_sheets)
                if not st.session_state.get("tasks_ready"):
                    st.session_state["tasks_ready"] = True
                    st.rerun()

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

                # Extract unique values for all auto-mapped fields
                unique_values = {
                    "revised": set(),
                    "status": set(),
                    "environment": set(),
                    "source": set()
                }
                for t in tasks:
                    if t.get("revised"):
                        unique_values["revised"].add(t["revised"])
                    if t.get("status"):
                        unique_values["status"].add(t["status"])
                    if t.get("environment"):
                        for env in t["environment"]:
                            unique_values["environment"].add(env)
                    if t.get("source"):
                        unique_values["source"].add(t["source"])

                st.session_state["excel_unique_values"] = unique_values

                # Show what values were found
                with st.expander("Field values found in Excel"):
                    for field, values in unique_values.items():
                        if values:
                            st.write(f"**{field}**: {', '.join(sorted(values))}")

                if unique_epics:
                    st.warning(f"Found {len(unique_epics)} unique Epic(s) - click **'Check Fields'** below to validate they exist in ClickUp")
            else:
                if st.session_state.get("tasks_ready"):
                    st.session_state["tasks_ready"] = False
                    st.rerun()

        except Exception as e:
            st.session_state["tasks_ready"] = False
            st.error(f"Error parsing Excel: {e}")
            import traceback
            st.code(traceback.format_exc())
    else:
        st.session_state["tasks_ready"] = False

# Tasks Preview
if tasks:
    with st.expander(f"Preview ({len(tasks)} tasks)", expanded=False):
        for i, task in enumerate(tasks[:10]):
            task_name = task.get('name', 'Unnamed')

            # Build compact field summary
            tags = []
            if task.get('epic'):
                tags.append(f"Epic: {task.get('epic')}")
            if task.get('status'):
                tags.append(task.get('status'))
            if task.get('environment'):
                env = task.get('environment')
                env_str = ", ".join(env) if isinstance(env, list) else env
                tags.append(env_str)

            if tags:
                st.text(f"{i+1}. {task_name}")
                st.caption(f"   {' | '.join(tags)}")
            else:
                st.text(f"{i+1}. {task_name}")

        if len(tasks) > 10:
            st.text(f"... and {len(tasks) - 10} more")

# ============================================================
# STEP 2: Validate ClickUp Fields
# ============================================================
if tasks:
    st.markdown("---")
    st.header("Step 2: Validate ClickUp Fields")

    if not api_token or not list_id:
        st.warning("Enter API Token and List ID in the sidebar first")
    else:
        if st.button("Check Fields", type="primary"):
            try:
                # Clear previous validation state
                st.session_state["missing_field_values"] = {}
                st.session_state["auto_map_fields"] = {}

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
                    epic_field = next((f for f in fields if f.get("name") == "Epic" and f.get("type") == "drop_down"), None)
                    if epic_field:
                        existing_options = {opt.get("name") for opt in epic_field.get("type_config", {}).get("options", [])}
                        missing_epics = required_epics - existing_options
                        st.session_state["missing_epics"] = missing_epics
                    else:
                        st.session_state["missing_epics"] = required_epics
                else:
                    st.session_state["missing_epics"] = set()

                st.success(f"Loaded {len(fields)} custom fields")

                # Check which Excel fields don't have matching ClickUp fields
                # Note: Status can be native task status, so handle it separately
                excel_fields_needing_match = {"Revised?", "Environment", "Source"}
                clickup_field_names = {f.get("name") for f in fields}
                unmatched = excel_fields_needing_match - clickup_field_names

                # Check if Status is a custom field or should use native status
                if "Status" not in clickup_field_names:
                    st.session_state["status_is_native"] = True
                else:
                    st.session_state["status_is_native"] = False

                if unmatched:
                    st.session_state["unmatched_fields"] = unmatched
                else:
                    st.session_state["unmatched_fields"] = set()

            except Exception as e:
                st.error(f"Error: {e}")

        # Show validation results
        if "field_status" in st.session_state:
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
                    st.markdown(f"- **{field['name']}** - Ready")
                elif field["exists"] and field.get("missing_options"):
                    st.markdown(f"- **{field['name']}** - Missing options")
                    with st.expander(f"Add missing options to {field['name']}"):
                        st.write(f"Missing: {', '.join(field['missing_options'])}")
                        st.write("Add these options in ClickUp, then click 'Check Fields' again.")
                else:
                    st.markdown(f"- **{field['name']}** - Not found")
                    with st.expander(f"How to create {field['name']}"):
                        for step in field.get("instructions", []):
                            st.markdown(step)

            # Show missing Epic options
            if missing_epics:
                st.markdown(f"- **Epic Options** - {len(missing_epics)} missing")
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
                st.markdown("- **Epic Options** - All values exist")

            # Show native status info
            if st.session_state.get("status_is_native"):
                st.markdown("- **Status** - Will use native ClickUp task status")

            # Show unmatched fields warning
            unmatched = st.session_state.get("unmatched_fields", set())
            if unmatched:
                st.warning(f"**Fields not found in ClickUp:** {', '.join(unmatched)}")
                st.caption("Create these custom fields in ClickUp to auto-map values from Excel")

# ============================================================
# STEP 3: Configure Custom Fields
# ============================================================
custom_field_values = {}
epic_field_info = None

if "custom_fields" in st.session_state and st.session_state["custom_fields"]:
    st.markdown("---")
    st.header("Step 3: Configure Custom Fields")

    fields = st.session_state["custom_fields"]

    for field in fields:
        field_name = field.get("name", "Unknown")
        field_id = field.get("id")
        field_type = field.get("type")

        # Check if there's a config default
        default_value = config.get("default_custom_fields", {}).get(field_name)

        # Special handling for Epic field when using Excel import
        if field_name == "Epic" and field_type == "drop_down" and input_method == "Upload Excel":
            st.info(f"**{field_name}** - Auto-populated from Excel Epics sheet")

            # Store Epic field info for task creation
            options = field.get("type_config", {}).get("options", [])
            epic_field_info = {
                "id": field_id,
                "options": {opt.get("name"): opt.get("id") for opt in options}
            }
            st.session_state["epic_field_info"] = epic_field_info
            continue

        # Auto-map fields from Excel columns (Revised?, Status, Environment, Source)
        auto_map_fields = {
            "Revised?": "revised",
            "Revised": "revised",
            "Status": "status",
            "Environment": "environment",
            "Source": "source"
        }

        if field_name in auto_map_fields and input_method == "Upload Excel":
            excel_key = auto_map_fields[field_name]

            # Store field info for auto-mapping
            if "auto_map_fields" not in st.session_state:
                st.session_state["auto_map_fields"] = {}

            options = field.get("type_config", {}).get("options", [])
            if field_type == "drop_down":
                dropdown_options = {opt.get("name"): opt.get("id") for opt in options}
                st.session_state["auto_map_fields"][excel_key] = {
                    "id": field_id,
                    "type": "drop_down",
                    "options": dropdown_options
                }

                # Validate Excel values against ClickUp dropdown options
                excel_values = st.session_state.get("excel_unique_values", {}).get(excel_key, set())
                if excel_values:
                    missing = []
                    matched = []
                    for val in excel_values:
                        if val in dropdown_options:
                            matched.append(val)
                        else:
                            missing.append(val)

                    if missing:
                        st.error(f"**{field_name}** - Missing options: {', '.join(missing)}")
                        st.session_state.setdefault("missing_field_values", {})[excel_key] = missing
                    else:
                        st.success(f"**{field_name}** - Auto-map from Excel ({', '.join(matched)})")

            elif field_type == "labels":
                # Store multiple matching options: exact, lowercase, and stripped (no emoji)
                label_options = {}
                label_options_lower = {}
                label_options_stripped = {}  # For matching without emojis

                emoji_pattern = re.compile(
                    "["
                    "\U0001F600-\U0001F64F"  # emoticons
                    "\U0001F300-\U0001F5FF"  # symbols & pictographs
                    "\U0001F680-\U0001F6FF"  # transport & map symbols
                    "\U0001F1E0-\U0001F1FF"  # flags
                    "\U00002702-\U000027B0"
                    "\U000024C2-\U0001F251"
                    "]+",
                    flags=re.UNICODE
                )

                for opt in options:
                    label = opt.get("label")
                    opt_id = opt.get("id")
                    if label:
                        label_options[label] = opt_id
                        label_options_lower[label.lower()] = opt_id
                        # Store stripped version (remove emojis and extra spaces)
                        stripped = emoji_pattern.sub('', label).strip()
                        label_options_stripped[stripped.lower()] = opt_id

                st.session_state["auto_map_fields"][excel_key] = {
                    "id": field_id,
                    "type": "labels",
                    "options": label_options,
                    "options_lower": label_options_lower,
                    "options_stripped": label_options_stripped
                }

                # Validate Excel values against ClickUp labels
                excel_values = st.session_state.get("excel_unique_values", {}).get(excel_key, set())
                if excel_values:
                    missing = []
                    matched = []
                    for val in excel_values:
                        # Try exact, lowercase, and stripped matching
                        if (val in label_options or
                            val.lower() in label_options_lower or
                            val.lower() in label_options_stripped):
                            matched.append(val)
                        else:
                            missing.append(val)

                    if missing:
                        st.error(f"**{field_name}** - Missing labels: {', '.join(missing)}")
                        st.session_state.setdefault("missing_field_values", {})[excel_key] = missing
                    else:
                        st.success(f"**{field_name}** - Auto-map from Excel ({', '.join(matched)})")

            elif field_type == "checkbox":
                # Checkbox field - "Yes" maps to True, anything else to False
                st.session_state["auto_map_fields"][excel_key] = {
                    "id": field_id,
                    "type": "checkbox"
                }
                st.success(f"**{field_name}** - Auto-map from Excel ('Yes' = checked)")

            continue

        # Enable checkbox for manual fields
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

            elif field_type == "labels":
                options = field.get("type_config", {}).get("options", [])
                # Labels use "label" property instead of "name"
                option_labels = [opt.get("label") for opt in options]

                if option_labels and any(option_labels):
                    # Parse default value (could be a list or comma-separated string)
                    default_selections = []
                    if default_value:
                        if isinstance(default_value, list):
                            default_selections = [v for v in default_value if v in option_labels]
                        elif isinstance(default_value, str):
                            default_selections = [v.strip() for v in default_value.split(",") if v.strip() in option_labels]

                    selected = st.multiselect(
                        field_name,
                        options=option_labels,
                        default=default_selections,
                        key=f"value_{field_id}",
                        help="Select one or more labels"
                    )

                    if selected:
                        # Labels field expects a list of option IDs
                        selected_ids = []
                        for opt in options:
                            if opt.get("label") in selected:
                                selected_ids.append(opt.get("id"))
                        custom_field_values[field_id] = selected_ids
                else:
                    st.warning(f"No labels defined for '{field_name}' - create labels in ClickUp first")

            else:
                st.info(f"Field type '{field_type}' - enter value manually")
                value = st.text_input(
                    field_name,
                    value=str(default_value) if default_value else "",
                    key=f"value_{field_id}"
                )
                if value:
                    custom_field_values[field_id] = value

# ============================================================
# STEP 4: Create Tasks
# ============================================================
st.markdown("---")
st.header("Step 4: Create Tasks")

if custom_field_values:
    with st.expander("Custom fields to apply"):
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
        st.warning("Click **'Check Fields'** in Step 2 to verify custom fields are set up.")
    elif not setup_complete:
        st.error("Some required custom fields are missing. See the validation results in Step 2.")

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
    # Also check that all Epic options exist and all field values are matched
    no_required_fields = not config.get("required_custom_fields")
    missing_epics = st.session_state.get("missing_epics", set())
    missing_field_values = st.session_state.get("missing_field_values", {})
    has_missing_values = any(missing_field_values.values())

    can_create = (setup_complete or no_required_fields) and len(missing_epics) == 0 and not has_missing_values

    # Show warnings for missing values
    if missing_epics:
        st.error(f"{len(missing_epics)} Epic option(s) missing in ClickUp. See validation results in Step 2.")

    if has_missing_values:
        for field_key, missing in missing_field_values.items():
            if missing:
                st.error(f"Missing '{field_key}' values: {', '.join(missing)} - add them in ClickUp first")

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

            # Add auto-mapped fields from Excel (Revised?, Status, Environment, Source)
            auto_map_fields = st.session_state.get("auto_map_fields", {})

            # Map Revised? field (can be checkbox or dropdown)
            if "revised" in auto_map_fields and task.get("revised"):
                field_info = auto_map_fields["revised"]
                if field_info["type"] == "checkbox":
                    # Checkbox: "Yes" → True, anything else → False
                    is_checked = task["revised"].lower() in ["yes", "true", "1"]
                    cf_list.append({"id": field_info["id"], "value": is_checked})
                elif field_info["type"] == "drop_down":
                    option_id = field_info["options"].get(task["revised"])
                    if option_id:
                        cf_list.append({"id": field_info["id"], "value": option_id})

            # Map Status field (can be custom field dropdown OR native task status)
            task_status = None
            if "status" in auto_map_fields and task.get("status"):
                field_info = auto_map_fields["status"]
                if field_info["type"] == "drop_down":
                    option_id = field_info["options"].get(task["status"])
                    if option_id:
                        cf_list.append({"id": field_info["id"], "value": option_id})
                elif field_info["type"] == "native":
                    # Native task status - will be passed separately
                    task_status = task["status"]
            elif task.get("status"):
                # No custom field found - assume it's native status
                task_status = task["status"]

            # Map Source field
            if "source" in auto_map_fields and task.get("source"):
                field_info = auto_map_fields["source"]
                option_id = field_info["options"].get(task["source"])
                if option_id:
                    cf_list.append({"id": field_info["id"], "value": option_id})

            # Map Environment field (labels/multi-select)
            if "environment" in auto_map_fields and task.get("environment"):
                field_info = auto_map_fields["environment"]
                if field_info["type"] == "labels":
                    # Labels field expects a list of option IDs
                    selected_ids = []
                    for env_val in task["environment"]:
                        # Try exact match first, then case-insensitive, then stripped (no emoji)
                        option_id = field_info["options"].get(env_val)
                        if not option_id and "options_lower" in field_info:
                            option_id = field_info["options_lower"].get(env_val.lower())
                        if not option_id and "options_stripped" in field_info:
                            option_id = field_info["options_stripped"].get(env_val.lower())
                        if option_id:
                            selected_ids.append(option_id)
                    if selected_ids:
                        cf_list.append({"id": field_info["id"], "value": selected_ids})
                elif field_info["type"] == "drop_down":
                    # For dropdown, just use the first value
                    option_id = field_info["options"].get(task["environment"][0])
                    if option_id:
                        cf_list.append({"id": field_info["id"], "value": option_id})

            success, msg = create_task(list_id, task_name, task_desc, cf_list, api_token, status=task_status)

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
