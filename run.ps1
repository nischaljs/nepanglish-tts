# nepanglish-tts — single-command entry point (Windows).
#
#   .\run.ps1                 # opens the REPL (sets up first if needed)
#   .\run.ps1 setup           # only do the setup, don't launch the REPL
#   .\run.ps1 -- <args...>    # run an arbitrary command in the project venv
#
# Self-contained: no system Python required, no admin rights. Everything
# — uv's downloaded interpreter, package cache, venv, voice model —
# lives inside this folder. Delete the folder to uninstall.

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# OneDrive sync corrupts Python venvs; refuse to run from inside one.
if ((Get-Location).Path -match "OneDrive") {
    Write-Host "ERROR: this repo lives inside OneDrive." -ForegroundColor Red
    Write-Host "OneDrive sync corrupts Python venvs. Move the folder somewhere"
    Write-Host "outside OneDrive (e.g. C:\dev\nepanglish-tts) and re-run."
    exit 1
}

# Keep uv's caches inside the project so deleting the folder = clean wipe.
$env:UV_CACHE_DIR = Join-Path $PWD ".uv\cache"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PWD ".uv\python"

$marker = ".venv\.setup_complete"
$venvPython = ".\.venv\Scripts\python.exe"

function Run-Setup {
    Write-Host ""
    Write-Host "=== nepanglish-tts: first-time setup ===" -ForegroundColor Cyan
    Write-Host "Everything stays inside this folder ($PWD)."
    Write-Host ""

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "Installing uv (one-time, ~30 MB)..." -ForegroundColor Cyan
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
    }
    Write-Host ("uv: " + (& uv --version)) -ForegroundColor Green

    Write-Host ""
    Write-Host "Provisioning Python 3.10 into .uv\python ..." -ForegroundColor Cyan
    & uv python install 3.10

    if (-not (Test-Path ".venv")) {
        Write-Host ""
        Write-Host "Creating .venv ..." -ForegroundColor Cyan
        & uv venv --python 3.10 .venv
    }

    Write-Host ""
    Write-Host "Installing CPU-only torch ..." -ForegroundColor Cyan
    & uv pip install --python $venvPython -r requirements-cpu.txt

    Write-Host ""
    Write-Host "Installing project requirements ..." -ForegroundColor Cyan
    & uv pip install --python $venvPython -r requirements.txt

    Write-Host ""
    Write-Host "Downloading the Nepali voice model ..." -ForegroundColor Cyan
    & $venvPython scripts\download_model.py

    New-Item -Path $marker -ItemType File -Force | Out-Null
    Write-Host ""
    Write-Host "Setup complete." -ForegroundColor Green
}

$cmd = if ($args.Length -ge 1) { $args[0] } else { "" }

switch ($cmd) {
    "setup" {
        Run-Setup
        exit 0
    }
    "daemon" {
        if (-not (Test-Path $marker)) { Run-Setup }
        $rest = if ($args.Length -gt 1) { $args[1..($args.Length - 1)] } else { @() }
        Write-Host ""
        Write-Host "Starting Nepali TTS HTTP daemon (Ctrl-C to stop)." -ForegroundColor Cyan
        Write-Host ""
        & $venvPython scripts\tts_daemon.py @rest
        exit $LASTEXITCODE
    }
    "--" {
        if (-not (Test-Path $marker)) { Run-Setup }
        $rest = if ($args.Length -gt 1) { $args[1..($args.Length - 1)] } else { @() }
        & $venvPython @rest
        exit $LASTEXITCODE
    }
    "" {
        if (-not (Test-Path $marker)) { Run-Setup }
        Write-Host ""
        Write-Host "Launching the type-and-hear REPL — type a sentence, hit Enter."
        Write-Host ""
        & $venvPython scripts\test_repl.py
        exit $LASTEXITCODE
    }
    default {
        Write-Host "Usage: .\run.ps1 [setup | daemon [--port N] | -- <cmd...>]" -ForegroundColor Yellow
        exit 2
    }
}
