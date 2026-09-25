from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    port = int(os.environ.get("DATABRICKS_APP_PORT", os.environ.get("PORT", "8000")))
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=False)
