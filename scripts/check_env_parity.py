import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from google.oauth2 import service_account
import google.auth.transport.requests

from app.core.config import Settings

CRED_PATH = r"d:\Projects\VlegalAI-227\env.json"
PROJECT_ID = "idyllic-anvil-452006-k0"
REGION = "asia-southeast1"
SERVICE_NAME = "vlegalai"

def main():
    # 1. Dynamically extract all setting fields from Settings model
    fields = set(Settings.model_fields.keys())

    # 2. Query Cloud Run service environment variables
    credentials = service_account.Credentials.from_service_account_file(
        CRED_PATH,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    token = credentials.token

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    url = f"https://run.googleapis.com/v2/projects/{PROJECT_ID}/locations/{REGION}/services/{SERVICE_NAME}"
    res = httpx.get(url, headers=headers)
    if res.status_code != 200:
        print(f"Error fetching Cloud Run service: {res.status_code} {res.text}")
        sys.exit(1)

    service_data = res.json()
    containers = service_data.get("template", {}).get("containers", [])
    set_env_vars = set()
    for c in containers:
        for env in c.get("env", []):
            name = env.get("name")
            if name:
                set_env_vars.add(name.lower())

    print(f"Total Settings Fields in Code: {len(fields)}")
    print(f"Total Env Vars set on Cloud Run '{SERVICE_NAME}': {len(set_env_vars)}")

    missing_env = sorted([f.upper() for f in fields if f.lower() not in set_env_vars])

    print("\n=== ENVIRONMENT VARIABLES NOT EXPLICITLY SET ON CLOUD RUN (FALLING BACK TO CODE DEFAULTS) ===")
    if not missing_env:
        print("ALL fields in Settings are explicitly set on Cloud Run!")
    else:
        for var in missing_env:
            print(f"- {var}")

if __name__ == "__main__":
    main()
