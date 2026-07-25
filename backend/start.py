"""
AppSail startup script — reads PORT from environment safely.
"""
import os
import sys

# Ensure backend dir is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

if __name__ == "__main__":
    port_env = (
        os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT") or
        os.environ.get("PORT") or
        os.environ.get("X_ZC_APP_PORT") or
        "8080"
    )
    port = int(port_env)
    print(f"[STARTUP] Starting AppSail server on port {port} (env: {port_env})", flush=True)
    from main import app
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
