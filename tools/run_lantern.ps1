# Windows launcher. Double-click run.bat: root, Nohup/Terminal, launch.
# Never overwrite host/port or user settings when a config already exists.
[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$SetupOnly,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Say([string]$Message) { Write-Host "[Lantern] $Message" }

function Read-YamlValue([string]$Source, [string]$Key) {
    $pattern = '(?m)^\s*' + [regex]::Escape($Key) + '\s*:\s*(.*)$'
    $match = [regex]::Match($Source, $pattern)
    if (-not $match.Success) { return $null }
    $raw = $match.Groups[1].Value.Trim()
    if ($raw.Length -ge 2 -and (($raw[0] -eq '"' -and $raw[-1] -eq '"') -or
                                ($raw[0] -eq "'" -and $raw[-1] -eq "'"))) {
        return $raw.Substring(1, $raw.Length - 2)
    }
    return $raw -replace '\s+#.*$', ''
}

function Find-Uv {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "Lantern\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\uv\uv.exe")
    )) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

function Ensure-Uv {
    $existing = Find-Uv
    if ($existing) { return $existing }

    Say "uv not found; downloading the official Windows release (one-time setup)..."
    $architecture = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { "aarch64" } else { "x86_64" }
    $url = "https://github.com/astral-sh/uv/releases/latest/download/uv-$architecture-pc-windows-msvc.zip"
    $destination = Join-Path $env:LOCALAPPDATA "Lantern\bin\uv.exe"
    $temporary = Join-Path ([IO.Path]::GetTempPath()) ("lantern-uv-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $temporary -Force | Out-Null
    try {
        $archive = Join-Path $temporary "uv.zip"
        $unpacked = Join-Path $temporary "extract"
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive
        Expand-Archive -LiteralPath $archive -DestinationPath $unpacked
        $exe = Get-ChildItem -LiteralPath $unpacked -Recurse -File -Filter "uv.exe" |
               Select-Object -First 1
        if (-not $exe) { throw "Official uv archive did not contain uv.exe." }
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $exe.FullName -Destination $destination -Force
    }
    finally {
        Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
    }
    return $destination
}

function Ensure-Python([string]$Repo) {
    $virtual = Join-Path $Repo ".venv"
    $python = Join-Path $virtual "Scripts\python.exe"
    $requirements = Join-Path $Repo "requirements.txt"
    if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
        throw "requirements.txt is missing; update/clone the complete Lantern repository."
    }

    $uv = $null
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        $uv = Ensure-Uv
        Say "Preparing Python 3.12 in .venv (first launch may download Python)..."
        & $uv venv --python 3.12 $virtual
        if ($LASTEXITCODE -ne 0) { throw "Cannot create the Python environment." }
    }

    # .NET hashing works on minimal PowerShell installations without Get-FileHash.
    $hasher = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($requirements)
    try { $digest = ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-', '') }
    finally { $stream.Dispose(); $hasher.Dispose() }
    $stamp = Join-Path $virtual ".lantern-requirements.sha256"
    $matches = (Test-Path $stamp) -and ((Get-Content -LiteralPath $stamp -Raw).Trim() -eq $digest)
    $valid = $false
    if ($matches) {
        & $python -c "import watchdog; import winpty" *> $null
        $valid = ($LASTEXITCODE -eq 0)
    }
    if (-not $valid) {
        if (-not $uv) { $uv = Ensure-Uv }
        Say "Installing/verifying runtime requirements..."
        & $uv pip install --python $python -r $requirements
        if ($LASTEXITCODE -ne 0) { throw "Dependency setup failed; check network or uv output." }
        & $python -c "import watchdog; import winpty"
        if ($LASTEXITCODE -ne 0) { throw "pywinpty/watchdog is missing from .venv." }
        [IO.File]::WriteAllText($stamp, $digest, [Text.UTF8Encoding]::new($false))
    }
    return $python
}

function Test-Listening([string]$HostAddress, [int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostAddress, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(450)) { return $false }
        $client.EndConnect($async)
        return $true
    }
    catch { return $false }
    finally { $client.Close() }
}

function Get-LanternInfo([string]$Url) {
    try {
        $info = Invoke-RestMethod -Uri ($Url + "/api/info") -Method Get -TimeoutSec 2
        if ($info.app -eq "LAN Drive OneFile" -and $info.root) { return $info }
    }
    catch { }
    return $null
}

function Open-Lantern([string]$Url) {
    try { Start-Process -FilePath $Url | Out-Null }
    catch { Say "Open this URL in your browser: $Url" }
}

function Main {
    $repo = [IO.Path]::GetFullPath($RepoRoot)
    if (-not (Test-Path -LiteralPath (Join-Path $repo "lan_drive.py") -PathType Leaf)) {
        throw "Not a Lantern checkout: $repo"
    }
    Set-Location -LiteralPath $repo

    $standard = Join-Path $repo "lan_drive_config.yaml"
    $local = Join-Path $repo "lan_drive_config.local.yaml"
    $template = Join-Path $repo "lan_drive_config.yaml_copy"
    $config = if (Test-Path -LiteralPath $standard) { $standard } elseif (Test-Path -LiteralPath $local) { $local } else { $standard }
    if (Test-Path -LiteralPath $config) {
        $source = [IO.File]::ReadAllText($config, [Text.Encoding]::UTF8)
    }
    else {
        if (-not (Test-Path -LiteralPath $template -PathType Leaf)) {
            throw "Configuration template is missing: $template"
        }
        $source = [IO.File]::ReadAllText($template, [Text.Encoding]::UTF8)
    }

    $defaultRoot = $env:USERPROFILE
    $existingRoot = Read-YamlValue $source "root"
    if ($existingRoot -and $existingRoot -ne ".") {
        $defaultRoot = $existingRoot -replace '\\\\', '\'
    }
    Say "Choose the directory Lantern can access."
    $root = $null
    while (-not $root) {
        $inputPath = Read-Host ("Root directory [{0}]" -f $defaultRoot)
        if ([string]::IsNullOrWhiteSpace($inputPath)) { $inputPath = $defaultRoot }
        $inputPath = [Environment]::ExpandEnvironmentVariables($inputPath.Trim().Trim('"'))
        try { $candidate = [IO.Path]::GetFullPath($inputPath) }
        catch { Say "Invalid directory path."; continue }
        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) {
            Say "Directory does not exist: $candidate"
            continue
        }
        $root = $candidate
    }

    Say "Choose how the server runs:"
    Write-Host "  [1] Nohup    - run in background; hide the server console"
    Write-Host "  [2] Terminal - keep a visible console for server output"
    $mode = $null
    while (-not $mode) {
        $selection = (Read-Host "Mode [1/2]").Trim().ToLowerInvariant()
        switch ($selection) {
            { $_ -in @("1", "n", "nohup", "nohop") } { $mode = "Nohup"; break }
            { $_ -in @("2", "t", "terminal") } { $mode = "Terminal"; break }
            default { Say "Enter 1 (Nohup) or 2 (Terminal)." }
        }
    }

    $hostValue = Read-YamlValue $source "host"
    if (-not $hostValue) { $hostValue = "127.0.0.1" }
    $rawPort = Read-YamlValue $source "port"
    $port = 9999
    if ($rawPort) {
        if (-not [int]::TryParse($rawPort, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
            throw "Invalid port in config: $rawPort"
        }
    }
    $probeHost = if ($hostValue -in @("0.0.0.0", "::", "localhost")) { "127.0.0.1" } else { $hostValue }
    $urlHost = if ($probeHost.Contains(":")) { "[$probeHost]" } else { $probeHost }
    $url = "http://${urlHost}:${port}"

    if (Test-Listening $probeHost $port) {
        $existing = Get-LanternInfo $url
        if (-not $existing) {
            throw "Port $port is already occupied by another server. Change the YAML port."
        }
        $runningRoot = [IO.Path]::GetFullPath([string]$existing.root)
        if (-not [string]::Equals($runningRoot.TrimEnd('\'), $root.TrimEnd('\'),
                                 [StringComparison]::OrdinalIgnoreCase)) {
            throw "Lantern is already running at $url with root '$runningRoot'. Stop it before switching roots."
        }
        Say "Lantern is already running at $url. Not launching a duplicate."
        if (-not $SetupOnly -and -not $NoBrowser) { Open-Lantern $url }
        return
    }

    # Persist the requested root while retaining every other machine setting.
    $normalizedRoot = $root.Replace('\', '/')
    $replacement = 'root: "' + $normalizedRoot + '"'
    $pattern = '(?m)^\s*root\s*:.*$'
    $rootLine = [regex]::new(
        $pattern, [Text.RegularExpressions.RegexOptions]::None, [TimeSpan]::FromSeconds(2)
    )
    if ($rootLine.IsMatch($source)) {
        $result = $rootLine.Replace($source, [System.Text.RegularExpressions.MatchEvaluator]{
            param($match) $replacement
        })
    }
    else {
        $result = $source.TrimEnd() + [Environment]::NewLine + $replacement + [Environment]::NewLine
    }

    if (-not (Test-Path -LiteralPath $config) -or $result -cne $source) {
        $temporaryConfig = $config + ".tmp-" + [guid]::NewGuid().ToString('N')
        try {
            [IO.File]::WriteAllText($temporaryConfig, $result, [Text.UTF8Encoding]::new($false))
            Move-Item -LiteralPath $temporaryConfig -Destination $config -Force
        }
        finally { Remove-Item -LiteralPath $temporaryConfig -Force -ErrorAction SilentlyContinue }
    }
    Say "Root:   $root"
    Say "Config: $config"
    Say "Mode:   $mode"
    Say "URL:    $url"
    if ($hostValue -notin @("127.0.0.1", "localhost", "::1")) {
        Say "WARNING: Lantern has no authentication; this host binding may expose files and commands to the network."
    }
    if ($SetupOnly) {
        Say "Setup-only verification complete. No process started."
        return
    }

    $python = Ensure-Python $repo
    $script = Join-Path $repo "lan_drive.py"
    $args = '-u "' + $script + '" --config "' + $config + '"'
    $start = @{
        FilePath = $python
        WorkingDirectory = $repo
        ArgumentList = $args
        WindowStyle = if ($mode -eq "Nohup") { "Hidden" } else { "Normal" }
        PassThru = $true
    }
    $errorsLog = $null
    if ($mode -eq "Nohup") {
        $logFolder = Join-Path $env:LOCALAPPDATA "Lantern\logs"
        New-Item -Path $logFolder -ItemType Directory -Force | Out-Null
        $label = (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString('N').Substring(0, 8)
        $outputLog = Join-Path $logFolder "server-$label.stdout.log"
        $errorsLog = Join-Path $logFolder "server-$label.stderr.log"
        $start["RedirectStandardOutput"] = $outputLog
        $start["RedirectStandardError"] = $errorsLog
        Say "Background logs: $logFolder"
    }

    $child = Start-Process @start
    Say "Server PID: $($child.Id)"
    $deadline = [DateTime]::UtcNow.AddSeconds(18)
    while ([DateTime]::UtcNow -lt $deadline) {
        $child.Refresh()
        if ($child.HasExited) { break }
        $info = Get-LanternInfo $url
        if ($info -and [string]::Equals(
            [IO.Path]::GetFullPath([string]$info.root).TrimEnd('\'), $root.TrimEnd('\'),
            [StringComparison]::OrdinalIgnoreCase)) {
            Say "Ready: $url"
            if (-not $NoBrowser) { Open-Lantern $url }
            return
        }
        Start-Sleep -Milliseconds 350
    }
    if ($errorsLog -and (Test-Path $errorsLog)) {
        $tail = Get-Content -LiteralPath $errorsLog -Tail 12
        if ($tail) { Write-Host ($tail -join [Environment]::NewLine) }
    }
    throw "Server did not become ready at $url. Check the console or background logs."
}

try { Main }
catch {
    Write-Host ("[Lantern] ERROR: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
