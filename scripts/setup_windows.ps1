# Windows setup for nepanglish-tts.
#
# Run from the repo root in PowerShell:
#     powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
#
# Bootstraps everything end-to-end: installs `uv` (single-binary Python
# toolchain), uses it to download a standalone Python 3.10 just for this
# project, creates the venv, installs deps in the right order. No system
# Python install, no admin rights, no PATH surgery.
#
# Why 3.10 specifically: fairseq (transitive dep of
# ai4bharat-transliteration) fails to import on Python 3.11+ due to a
# stricter @dataclass mutable-default check. See mise.toml.

$ErrorActionPreference = "Stop"

$repo = (Get-Location).Path
Write-Host ""
Write-Host "=== nepanglish-tts Windows setup ===" -ForegroundColor Cyan
Write-Host "Repo path: $repo"
Write-Host ""

# 1. Refuse to run from inside OneDrive — sync corrupts Python venvs.
if ($repo -match "OneDrive") {
    Write-Host "ERROR: this repo lives inside OneDrive." -ForegroundColor Red
    Write-Host "OneDrive sync corrupts Python venvs. Move the repo somewhere"
    Write-Host "outside OneDrive (e.g. C:\dev\nepanglish-tts) and re-run."
    exit 1
}

# 2. Install uv if missing. Drops a single exe into %USERPROFILE%\.local\bin.
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv (one-time, ~30 MB)..." -ForegroundColor Cyan
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
}
$uvVersion = & uv --version
Write-Host "uv: $uvVersion" -ForegroundColor Green

# 3. Fetch a standalone Python 3.10 just for this project.
Write-Host ""
Write-Host "Provisioning Python 3.10..." -ForegroundColor Cyan
& uv python install 3.10

# 4. Create the venv pointing at that 3.10.
if (-not (Test-Path ".venv")) {
    Write-Host "Creating .venv..." -ForegroundColor Cyan
    & uv venv --python 3.10 .venv
} else {
    Write-Host ".venv already exists, reusing it." -ForegroundColor Yellow
}

# 5. CPU-only torch FIRST — saves ~2 GB of unused CUDA libs. uv's
#    resolver handles fairseq's broken metadata, so no pip pinning needed.
Write-Host ""
Write-Host "Installing CPU-only torch (slow step, be patient)..." -ForegroundColor Cyan
$env:VIRTUAL_ENV = ".venv"
& uv pip install -r requirements-cpu.txt

# 6. Project deps.
Write-Host ""
Write-Host "Installing project requirements..." -ForegroundColor Cyan
& uv pip install -r requirements.txt

# 7. Voice model.
Write-Host ""
Write-Host "Downloading the Nepali voice model (~60 MB)..." -ForegroundColor Cyan
& .\.venv\Scripts\python.exe scripts\download_model.py

Write-Host ""
Write-Host "Done. Activate with:" -ForegroundColor Green
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "Then try:"
Write-Host "    python scripts\test_repl.py"
