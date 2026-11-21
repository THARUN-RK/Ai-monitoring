# Powershell launcher for CICADA Customer Collector Agent
Write-Host "Starting CICADA Tier 1 Customer Agent..." -ForegroundColor Cyan

# Locate best python executable with psutil/requests
$py312 = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$py314 = "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe"

if (Test-Path $py312) {
    & $py312 customer-agent/app/main.py
} elseif (Test-Path $py314) {
    & $py314 customer-agent/app/main.py
} else {
    py -3 customer-agent/app/main.py
}
