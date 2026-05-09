# Windows setup script for nepanglish-tts.
#
# Run from the repo root in PowerShell:
#     powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
#
# Handles the three things that bite Windows users on a fresh clone:
#   1. OneDrive paths corrupt Python venvs (file locks during sync).
#   2. Default pip timeout is too short for fairseq's huge transitive deps.
#   3. CPU-only torch must be installed BEFORE ai4bharat-transliteration,
#      or pip pulls 2 GB of unused CUDA libs.

$ErrorActionPreference = "Stop"

$repo = (Get-Location).Path
Write-Host ""
Write-Host "=== nepanglish-tts Windows setup ===" -ForegroundColor Cyan
Write-Host "Repo path: $repo"
Write-Host ""

# 1. Refuse to run from inside OneDrive.
if ($repo -match "OneDrive") {
    Write-Host "ERROR: this repo lives inside OneDrive." -ForegroundColor Red
    Write-Host "OneDrive sync corrupts Python venvs. Move the repo somewhere"
    Write-Host "outside OneDrive (e.g. C:\dev\nepanglish-tts) and re-run."
    exit 1
}

# 2. Find Python 3.10. Newer Pythons make the ancient `regex` sdist
#    (transitive dep) harder to build on Windows.
$python = $null
foreach ($candidate in @("py -3.10", "python3.10", "python")) {
    try {
        $version = & cmd /c "$candidate --version 2>&1"
        if ($version -match "Python 3\.10\.") {
            $python = $candidate
            Write-Host "Using: $candidate ($version)" -ForegroundColor Green
            break
        }
    } catch { }
}
if (-not $python) {
    Write-Host "ERROR: Python 3.10 not found." -ForegroundColor Red
    Write-Host "Install it from https://www.python.org/downloads/release/python-31011/"
    Write-Host "(this project pins 3.10; 3.11+ makes some old transitive deps fail to build)"
    exit 1
}

# 3. Create venv if missing.
if (-not (Test-Path ".venv")) {
    Write-Host "Creating .venv..." -ForegroundColor Cyan
    & cmd /c "$python -m venv .venv"
} else {
    Write-Host ".venv already exists, reusing it." -ForegroundColor Yellow
}

$pip = ".\.venv\Scripts\pip.exe"
$venvPython = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $pip)) {
    Write-Host "ERROR: venv creation failed (no pip.exe)." -ForegroundColor Red
    exit 1
}

# 4. Pin pip to a version that's permissive about fairseq's metadata
#    and bump the network timeout so big sdist downloads survive a
#    flaky link.
Write-Host ""
Write-Host "Pinning pip < 24.1 and raising network timeout to 300s..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade "pip<24.1"
& $pip config set global.timeout 300

# 5. CPU-only torch FIRST — saves ~2 GB of unused CUDA libs.
Write-Host ""
Write-Host "Installing CPU-only torch (this is the slow step, be patient)..." -ForegroundColor Cyan
& $pip install --default-timeout=300 --retries 5 -r requirements-cpu.txt

# 6. Project deps.
Write-Host ""
Write-Host "Installing project requirements..." -ForegroundColor Cyan
& $pip install --default-timeout=300 --retries 5 -r requirements.txt

# 7. Voice model.
Write-Host ""
Write-Host "Downloading the Nepali voice model (~60 MB)..." -ForegroundColor Cyan
& $venvPython scripts\download_model.py

Write-Host ""
Write-Host "Done. Activate with:" -ForegroundColor Green
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "Then try:"
Write-Host "    python scripts\test_repl.py"
