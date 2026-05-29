# Launch the ODOT Title Forms web app.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $here ".venv\Scripts\python.exe"
& $py -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --app-dir $here
