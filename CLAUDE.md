# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python scripts for bulk task management via the ClickUp API v2.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file with your ClickUp API token (for CLI scripts):
```
API_TOKEN=your_clickup_api_token_here
```

For the web UI, use `.streamlit/secrets.toml` instead:
```toml
API_TOKEN = "your_clickup_api_token_here"
```

## Commands

### Web UI (Recommended)
```bash
streamlit run app.py
```
Browser-based interface with customizable custom fields. Can be deployed to Streamlit Cloud for team access.

### CLI - Bulk Create Tasks
```bash
py bulkcreatetasks.py <LIST_ID> <JSON_FILE_PATH>
```
Creates tasks from a JSON file. The JSON should be an array of objects with `name` and optional `description` fields. Automatically sets the "Source" custom field to "Internal" if that field exists on the list.

### CLI - Bulk Delete Tasks
```bash
py bulkdeletetasks.py <LIST_ID>
```
Deletes ALL tasks in a ClickUp list. Requires typing "DELETE" to confirm.

## Deployment (Streamlit Cloud)

1. Push to GitHub
2. Connect at share.streamlit.io
3. Add `API_TOKEN` in Streamlit secrets
4. Share URL with team

## Architecture

- `app.py` - Streamlit web UI for bulk task creation with customizable custom fields
- `clickup_api.py` - Shared API functions used by both CLI and web UI
- `config.json` - Default custom field values (field name -> value mapping)
- CLI scripts use the ClickUp API v2 (`api.clickup.com/api/v2/`)
- Authentication via `Authorization` header with API token
