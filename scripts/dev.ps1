param(
    [int]$Port = 8010,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$env:PYTHONIOENCODING = "utf-8"

$args = @("-m", "uvicorn", "travel_advisor.app:app", "--host", "127.0.0.1", "--port", "$Port")
if ($Reload) { $args += "--reload" }

Write-Host "出行建议官 → http://127.0.0.1:$Port" -ForegroundColor Cyan
python @args
