[CmdletBinding()]
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Lantern",
    [string]$Root = $env:USERPROFILE,
    [ValidateRange(1, 65535)]
    [int]$Port = 9999,
    [string]$HostAddress = "",
    [switch]$BindAll,
    [switch]$EnableTerminal,
    [switch]$NoStart,
    [string]$Repo = "Hiroshimeow/lantern",
    [string]$Ref = "main"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Step([string]$Message) {
    Write-Host "[Lantern] $Message"
}

function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidates = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\uv\uv.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Ensure-Uv {
    $uv = Find-Uv
    if ($uv) { return $uv }

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Step "uv not found; installing astral-sh.uv with winget..."
        & $winget.Source install --id astral-sh.uv -e --source winget --accept-source-agreements --accept-package-agreements --silent
        $uv = Find-Uv
        if ($uv) { return $uv }
        $wingetLink = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\uv.exe"
        if (Test-Path $wingetLink) { return $wingetLink }
    }

    Write-Step "winget path unavailable; downloading the official uv Windows release..."
    $binDir = Join-Path $env:LOCALAPPDATA "Lantern\bin"
    $tmpDir = Join-Path ([IO.Path]::GetTempPath()) ("lantern-uv-" + [Guid]::NewGuid().ToString("N"))
    $tmpZip = Join-Path $tmpDir "uv.zip"
    $tmpExtract = Join-Path $tmpDir "extract"
    New-Item -ItemType Directory -Force -Path $binDir, $tmpExtract | Out-Null
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile $tmpZip
        Expand-Archive -LiteralPath $tmpZip -DestinationPath $tmpExtract -Force
        $uvSource = Get-ChildItem -LiteralPath $tmpExtract -Filter "uv.exe" -File -Recurse | Select-Object -First 1
        if (-not $uvSource) { throw "Downloaded uv archive does not contain uv.exe." }
        $uvTarget = Join-Path $binDir "uv.exe"
        Copy-Item -LiteralPath $uvSource.FullName -Destination $uvTarget -Force
        return $uvTarget
    }
    finally {
        if (Test-Path $tmpDir) {
            Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-SafeDefaultHost {
    # Lantern has no authentication, so installation must never expose it to
    # LAN/Tailscale implicitly. Remote binding is an explicit operator choice.
    return "127.0.0.1"
}

function Yaml-Quote([string]$Value) {
    return '"' + $Value.Replace('\', '\\').Replace('"', '\"') + '"'
}

$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$Root = [IO.Path]::GetFullPath($Root)

if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    throw "Root directory does not exist: $Root"
}

if ($BindAll) {
    $HostAddress = "0.0.0.0"
} elseif ([string]::IsNullOrWhiteSpace($HostAddress)) {
    $HostAddress = Get-SafeDefaultHost
}

$uv = Ensure-Uv
Write-Step "Using uv: $uv"
Write-Step "Install directory: $InstallDir"
Write-Step "Shared root: $Root"
Write-Step ("Bind address: {0}:{1}" -f $HostAddress, $Port)

$work = Join-Path ([IO.Path]::GetTempPath()) ("lantern-install-" + [Guid]::NewGuid().ToString("N"))
$zip = Join-Path $work "lantern.zip"
$extract = Join-Path $work "extract"
$appDir = Join-Path $InstallDir "app"
$venvDir = Join-Path $InstallDir ".venv"
$configPath = Join-Path $InstallDir "lan_drive_config.local.yaml"
$runBat = Join-Path $InstallDir "Run-Lantern.bat"
$cacheDir = Join-Path $env:LOCALAPPDATA "Lantern\cache"

try {
    New-Item -ItemType Directory -Force -Path $work, $extract, $InstallDir, $cacheDir | Out-Null

    $archiveUrl = "https://github.com/$Repo/archive/refs/heads/$Ref.zip"
    Write-Step "Downloading $Repo@$Ref..."
    Invoke-WebRequest -UseBasicParsing -Uri $archiveUrl -OutFile $zip
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force

    $sourceDir = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1
    if (-not $sourceDir -or -not (Test-Path (Join-Path $sourceDir.FullName "lan_drive.py"))) {
        throw "Downloaded archive does not contain lan_drive.py."
    }

    if (Test-Path $appDir) {
        Remove-Item -LiteralPath $appDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $appDir | Out-Null
    Copy-Item -Path (Join-Path $sourceDir.FullName "*") -Destination $appDir -Recurse -Force

    Write-Step "Preparing managed Python 3.12..."
    & $uv python install 3.12
    if ($LASTEXITCODE -ne 0) { throw "uv python install failed." }

    if (Test-Path $venvDir) {
        Remove-Item -LiteralPath $venvDir -Recurse -Force
    }
    & $uv venv --no-project --python 3.12 $venvDir
    if ($LASTEXITCODE -ne 0) { throw "uv venv failed." }

    $pythonExe = Join-Path $venvDir "Scripts\python.exe"
    & $uv pip install --python $pythonExe -r (Join-Path $appDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

    $terminalEnabled = if ($EnableTerminal) { "true" } else { "false" }
    $config = @"
# Generated by install.ps1. Machine-local configuration.
root: $(Yaml-Quote $Root)
port: $Port
host: $(Yaml-Quote $HostAddress)
title: "Lantern"
cache_dir: $(Yaml-Quote $cacheDir)
show_hidden: true
show_system: false
default_sort: "name-asc"
default_view: "grid"
page_limit: 100
folders_first: true
search_debounce_ms: 240
terminal_enabled: $terminalEnabled
terminal_max_sessions: 16
terminal_max_buffer_chars: 204800
terminal_start_height_px: 380
terminal_mobile_extra_keys: true
thumb_fit: "cover"
folder_preview_enabled: false
folder_preview_mode: "mosaic4"
folder_preview_fit: "cover"
folder_preview_rotate: true
folder_preview_animation: "fade"
folder_preview_interval_ms: 3500
folder_preview_scan_limit: 80
folder_preview_max_items: 24
folder_preview_include_video: true
upload_auto_start: false
upload_parallel: 3
upload_conflict: "ask"
"@
    Set-Content -LiteralPath $configPath -Value $config -Encoding UTF8

    $runContent = @"
@echo off
setlocal
cd /d "%~dp0app"
"%~dp0.venv\Scripts\python.exe" lan_drive.py --config "%~dp0lan_drive_config.local.yaml"
"@
    Set-Content -LiteralPath $runBat -Value $runContent -Encoding ASCII

    Write-Step "Validating installation..."
    & $pythonExe (Join-Path $appDir "lan_drive.py") --help *> $null
    if ($LASTEXITCODE -ne 0) { throw "Lantern validation failed." }

    $urlHost = if ($HostAddress -eq "0.0.0.0") { "127.0.0.1" } else { $HostAddress }
    $url = "http://" + $urlHost + ":" + $Port

    Write-Step "Installed successfully."
    Write-Host "  Run:    $runBat"
    Write-Host "  Config: $configPath"
    Write-Host "  URL:    $url"

    if ($HostAddress -eq "0.0.0.0") {
        Write-Warning "Lantern has no authentication. Binding to 0.0.0.0 exposes file operations to reachable networks."
    }
    if ($EnableTerminal) {
        Write-Warning "Terminal is enabled. Anyone who can reach Lantern can execute commands as this Windows user."
    }

    if (-not $NoStart) {
        Write-Step "Starting Lantern..."
        Start-Process -FilePath $runBat -WorkingDirectory $InstallDir
    }
}
finally {
    if (Test-Path $work) {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}
