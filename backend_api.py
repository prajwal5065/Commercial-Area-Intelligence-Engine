import os
import sys
import importlib.util

# Locate the actual backend_api.py in the Master Agent folder
_HERE = os.path.dirname(os.path.abspath(__file__))
_MASTER_AGENT_PATH = os.path.join(_HERE, "Master Agent")
_ACTUAL_API_PATH = os.path.join(_MASTER_AGENT_PATH, "backend_api.py")

# Prepend the Master Agent directory so the sub-agent module imports inside actual backend_api work
if _MASTER_AGENT_PATH not in sys.path:
    sys.path.insert(0, _MASTER_AGENT_PATH)

# Load the module under a different namespace to prevent circular import issues
spec = importlib.util.spec_from_file_location("actual_backend_api", _ACTUAL_API_PATH)
actual_backend_api = importlib.util.module_from_spec(spec)
sys.modules["actual_backend_api"] = actual_backend_api
spec.loader.exec_module(actual_backend_api)

# Expose the FastAPI app object for uvicorn
app = actual_backend_api.app

if __name__ == "__main__":
    import uvicorn
    # Use app_dir so reload and imports resolve correctly
    uvicorn.run("backend_api:app", host="0.0.0.0", port=8000, reload=True, app_dir=_MASTER_AGENT_PATH)
