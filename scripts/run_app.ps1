<#
.SYNOPSIS
    AirAlert Windows launcher — starts MLflow, FastAPI, and Next.js dashboard.

.DESCRIPTION
    Orchestrates the full AirAlert stack with one command:
    - Checks prerequisites (.venv, Node.js, Python)
    - Clears demo ports (5001, 8000, 3000)
    - Starts MLflow tracking server
    - Seeds synthetic PM2.5 data if missing
    - Bootstraps Production models if missing
    - Starts FastAPI serving layer
    - Installs dashboard dependencies and starts Next.js dev server
    - Opens the dashboard URL in the default browser
    - Monitors all services and exits on Ctrl+C with cleanup

.PARAMETER Clean
    Optional: pass -Clean to remove MLflow database, artifacts, and build caches before starting.
    Useful for resetting state on a fresh setup.
#>

param(
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'

# ─────────────────────────────────────────────────────────────────────────────
# Setup paths and configuration
# ─────────────────────────────────────────────────────────────────────────────

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogsDir = Join-Path $RepoRoot 'logs'
$VenvScripts = Join-Path $RepoRoot '.venv\Scripts'
$DashboardDir = Join-Path $RepoRoot 'app\dashboard'
$RawDir = Join-Path $RepoRoot 'include\data\raw'
$FeaturesDir = Join-Path $RepoRoot 'include\data\features'
$ModelsDir = Join-Path $RepoRoot 'include\models'
$PythonExe = Join-Path $VenvScripts 'python.exe'

# Service ports and URLs
$MlflowPort = 5001
$FastApiPort = 8000
$DashboardPort = 3000
$MlflowUrl = 'http://127.0.0.1:5001'
$FastApiUrl = 'http://127.0.0.1:8000'
$DashboardUrl = 'http://127.0.0.1:3000'

Set-Location $RepoRoot

# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

function Write-Step {
    param([string]$Message)
    Write-Host "[airalert] $Message"
}

# Throw an error with a message
function Fail {
    param([string]$Message)
    throw $Message
}

# Poll a URL until it returns an accepted status code, with timeout
function Test-UrlReady {
    param(
        [string]$Url,
        [int[]]$AcceptStatusCodes = @(200),
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $statusCode = 0
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            $statusCode = [int]$response.StatusCode
        }
        catch {
            $response = $_.Exception.Response
            if ($null -ne $response) {
                $statusCode = [int]$response.StatusCode
            }
        }

        if ($AcceptStatusCodes -contains $statusCode) {
            return $true
        }

        Start-Sleep -Seconds 1
    }

    return $false
}

# Find and kill any process listening on the given port
function Stop-PortListener {
    param([int]$Port)

    $connections = @()
    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    }
    catch {
        $connections = @()
    }

    foreach ($connection in $connections) {
        if ($null -ne $connection.OwningProcess) {
            Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }

    Start-Sleep -Milliseconds 300
}

# Run a command synchronously and wait for it to complete; fail if exit code != 0
function Invoke-LoggedCommand {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$StdOutPath,
        [string]$StdErrPath
    )

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $StdOutPath `
        -RedirectStandardError $StdErrPath `
        -PassThru `
        -Wait

    if ($process.ExitCode -ne 0) {
        Fail "Command failed with exit code $($process.ExitCode). See $StdOutPath and $StdErrPath."
    }
}

# Start a background process asynchronously (e.g., for services that stay running)
function Start-LoggedProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$StdOutPath,
        [string]$StdErrPath
    )

    return Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $StdOutPath `
        -RedirectStandardError $StdErrPath `
        -PassThru
}

# List all pm25_YYYY-MM-DD.csv files in the raw data directory
function Get-ExistingDailyRawFiles {
    if (-not (Test-Path $RawDir)) {
        return @()
    }

    Get-ChildItem -Path $RawDir -File -Filter 'pm25_*.csv' |
        Where-Object { $_.Name -match '^pm25_\d{4}-\d{2}-\d{2}\.csv$' }
}

# Extract the date (YYYY-MM-DD) from the most recent pm25_*.csv file
function Get-LatestRawDate {
    $latestFile = Get-ExistingDailyRawFiles |
        Sort-Object Name |
        Select-Object -Last 1

    if ($null -eq $latestFile) {
        return $null
    }

    return [System.IO.Path]::GetFileNameWithoutExtension($latestFile.Name).Substring(5)
}

# Check if Production models for all three locations exist in MLflow
function Test-ProductionModelsPresent {
    $checkScript = @'
import os
from mlflow.tracking import MlflowClient

client = MlflowClient(tracking_uri=os.environ.get("MLFLOW_TRACKING_URI"))
locations = ["red_butte", "smithfield", "ledges"]

for location in locations:
    model_name = f'AirAlert_{location}'
    try:
        versions = client.get_latest_versions(model_name, stages=["Production"])
        if not versions:
            print("yes")
            raise SystemExit(0)
    except Exception:
        print("yes")
        raise SystemExit(0)

print("no")
'@

    $tempScriptPath = [System.IO.Path]::GetTempFileName() + '.py'
    try {
        Set-Content -Path $tempScriptPath -Value $checkScript -Encoding utf8
        $result = & $PythonExe $tempScriptPath
        return ($result.Trim() -eq 'yes')
    }
    finally {
        Remove-Item $tempScriptPath -Force -ErrorAction SilentlyContinue
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Prerequisite checks
# ─────────────────────────────────────────────────────────────────────────────

if (-not (Test-Path (Join-Path $RepoRoot '.venv'))) {
    Fail ".venv not found at $RepoRoot. Create it with python -m venv .venv and install requirements.txt first."
}

if (-not (Test-Path $PythonExe)) {
    Fail "Python executable not found at $PythonExe."
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Fail 'npm.cmd not found on PATH. Install Node.js 20+ first.'
}

# Create logs directory and clear old logs
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
foreach ($logName in @('mlflow.log', 'fastapi.log', 'dashboard.log', 'bootstrap.log')) {
    $logPath = Join-Path $LogsDir $logName
    if (Test-Path $logPath) {
        Remove-Item $logPath -Force
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Clean up any existing services on the demo ports
# ─────────────────────────────────────────────────────────────────────────────

Write-Step 'Clearing demo ports...'
Stop-PortListener -Port $MlflowPort
Stop-PortListener -Port $FastApiPort
Stop-PortListener -Port $DashboardPort

if ($Clean) {
    Write-Step 'Cleaning local state...'
    Remove-Item (Join-Path $RepoRoot 'mlflow.db') -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $RepoRoot 'mlartifacts') -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $RepoRoot 'mlruns') -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $DashboardDir '.next') -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $FeaturesDir 'features_*.csv') -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $ModelsDir 'metrics_*.json') -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $ModelsDir '*.pkl') -Force -ErrorAction SilentlyContinue
}

$env:MLFLOW_TRACKING_URI = $MlflowUrl

Write-Step 'Starting MLflow tracking server...'
# Use relative paths since we're already in $RepoRoot
$mlflowProcess = Start-LoggedProcess -FilePath $PythonExe -ArgumentList @(
    '-m', 'mlflow', 'server',
    '--backend-store-uri', 'sqlite:///./mlflow.db',
    '--artifacts-destination', './mlartifacts',
    '--serve-artifacts',
    '--host', '127.0.0.1',
    '--port', "$MlflowPort"
) -WorkingDirectory $RepoRoot -StdOutPath (Join-Path $LogsDir 'mlflow.out.log') -StdErrPath (Join-Path $LogsDir 'mlflow.err.log')

if (-not (Test-UrlReady -Url $MlflowUrl -TimeoutSeconds 60)) {
    Fail "MLflow did not become ready at $MlflowUrl. Check $(Join-Path $LogsDir 'mlflow.out.log') and $(Join-Path $LogsDir 'mlflow.err.log')."
}

# Seed synthetic PM2.5 data if no raw data exists
$rawFiles = Get-ExistingDailyRawFiles
if ($rawFiles.Count -eq 0) {
    Write-Step 'Seeding synthetic raw data for first-time training...'
    Invoke-LoggedCommand -FilePath $PythonExe -ArgumentList @('scripts\seed_synthetic_raw.py') -WorkingDirectory $RepoRoot -StdOutPath (Join-Path $LogsDir 'bootstrap.out.log') -StdErrPath (Join-Path $LogsDir 'bootstrap.err.log')
}

$bootstrapDate = Get-LatestRawDate
if ($null -eq $bootstrapDate) {
    Fail 'No raw PM2.5 files are available for bootstrap training.'
}

# Train and register models if they don't exist in MLflow
if (Test-ProductionModelsPresent) {
    Write-Step 'Production models already exist in MLflow. Skipping bootstrap training.'
}
else {
    Write-Step 'Bootstrapping model training and registry promotion...'
    Invoke-LoggedCommand -FilePath $PythonExe -ArgumentList @('scripts\bootstrap_train.py', $bootstrapDate) -WorkingDirectory $RepoRoot -StdOutPath (Join-Path $LogsDir 'bootstrap.out.log') -StdErrPath (Join-Path $LogsDir 'bootstrap.err.log')
    Start-Sleep -Seconds 2
}

Write-Step 'Starting FastAPI serving layer...'
$fastapiProcess = Start-LoggedProcess -FilePath $PythonExe -ArgumentList @(
    '-m', 'uvicorn', 'include.src.serve:app',
    '--host', '127.0.0.1',
    '--port', "$FastApiPort"
) -WorkingDirectory $RepoRoot -StdOutPath (Join-Path $LogsDir 'fastapi.out.log') -StdErrPath (Join-Path $LogsDir 'fastapi.err.log')

if (-not (Test-UrlReady -Url ("$FastApiUrl/health") -AcceptStatusCodes @(200) -TimeoutSeconds 90)) {
    Fail "FastAPI did not become ready at $FastApiUrl. Check $(Join-Path $LogsDir 'fastapi.out.log') and $(Join-Path $LogsDir 'fastapi.err.log')."
}

Write-Step 'Starting Next.js dashboard...'
if (-not (Test-Path (Join-Path $DashboardDir 'node_modules'))) {
    Write-Step 'Installing dashboard dependencies (first run)...'
    & npm.cmd install *> (Join-Path $LogsDir 'dashboard.log')
    if ($LASTEXITCODE -ne 0) {
        Fail "npm install failed. Check $(Join-Path $LogsDir 'dashboard.log')."
    }
}

$env:FASTAPI_URL = $FastApiUrl
$env:RAW_DATA_DIR = $RawDir
$dashboardProcess = Start-LoggedProcess -FilePath 'npm.cmd' -ArgumentList @('run', 'dev') -WorkingDirectory $DashboardDir -StdOutPath (Join-Path $LogsDir 'dashboard.out.log') -StdErrPath (Join-Path $LogsDir 'dashboard.err.log')

if (-not (Test-UrlReady -Url $DashboardUrl -TimeoutSeconds 90)) {
    Fail "Dashboard did not become ready at $DashboardUrl. Check $(Join-Path $LogsDir 'dashboard.out.log') and $(Join-Path $LogsDir 'dashboard.err.log')."
}

try {
    Start-Process $DashboardUrl
}
catch {
    Write-Step "Dashboard is up, but the browser did not open automatically. Visit $DashboardUrl manually."
}

Write-Host ''
Write-Host 'AirAlert stack is up.'
Write-Host "  Dashboard:      $DashboardUrl"
Write-Host "  FastAPI docs:   $FastApiUrl/docs"
Write-Host "  MLflow UI:      $MlflowUrl"
Write-Host ''
Write-Host "Logs are in $LogsDir"
Write-Host 'Use Ctrl+C to stop this launcher; it will clean up the child processes it started.'
Write-Host ''

try {
    # ─────────────────────────────────────────────────────────────────────────
    # Monitor all services
    # ─────────────────────────────────────────────────────────────────────────
    # Check every 2 seconds if services are still running. Ctrl+C triggers the
    # finally block for cleanup.
    while ($true) {
        $deadProcess = $null
        
        if ($null -ne $mlflowProcess -and $mlflowProcess.HasExited) {
            $deadProcess = "MLflow"
        }
        elseif ($null -ne $fastapiProcess -and $fastapiProcess.HasExited) {
            $deadProcess = "FastAPI"
        }
        elseif ($null -ne $dashboardProcess -and $dashboardProcess.HasExited) {
            $deadProcess = "Dashboard"
        }
        
        if ($null -ne $deadProcess) {
            Fail "$deadProcess service crashed. Check logs in $LogsDir"
        }
        
        Start-Sleep -Seconds 2
    }
}
catch [System.OperationCanceledException] {
    Write-Host "`n[airalert] Shutting down..."
}
finally {
    # Kill all spawned services and free up the ports
    foreach ($process in @($mlflowProcess, $fastapiProcess, $dashboardProcess)) {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }

    Stop-PortListener -Port $MlflowPort
    Stop-PortListener -Port $FastApiPort
    Stop-PortListener -Port $DashboardPort
}
