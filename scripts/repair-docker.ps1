# Recover Docker Desktop from the stale-socket crash.
#
# THE FAILURE, which has now happened four times on this machine:
#
#   Docker Desktop starts, one of its services tries to bind a unix socket in
#   %LOCALAPPDATA%, finds a zero-byte socket left behind by the previous run,
#   cannot delete it, and the whole backend crashes with an error dialog:
#
#     starting services: initializing Inference manager: listening on
#     unix://.../dockerInference: remove .../dockerInference: The file cannot
#     be accessed by the system.
#
#   The engine never comes up, so postgres-local and redis-local never start,
#   so the API cannot boot and the whole stack looks broken for a reason that
#   has nothing to do with this project.
#
# TWO SERVICES DO IT, and clearing only one just moves the crash: the
# Inference manager (Docker AI) under Docker\run, and the Secrets Engine under
# docker-secrets-engine. Both directories are cleared here, which is why the
# list is a list rather than a single path.
#
# WHY NOT JUST TURN THE FEATURE OFF: EnableDockerAI is already false in
# settings-store.json and the Inference manager starts anyway. There is no
# setting for it in 4.78.
#
# WHY THE DIRECTORY IS RENAMED RATHER THAN THE FILE DELETED: the stale sockets
# are orphaned AF_UNIX reparse points. Remove-Item, [System.IO.File]::Delete
# and `del /f` all fail with "the file cannot be accessed by the system".
# Renaming the parent directory works, and Docker recreates it on start.
#
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\repair-docker.ps1

$ErrorActionPreference = 'Stop'

# Docker Desktop can take several minutes on a cold start on this machine.
$TimeoutMinutes = 8

function Test-DockerEngine {
    $job = Start-Job { & docker ps --format '{{.Names}}' 2>&1 }
    $done = Wait-Job $job -Timeout 20
    $ok = $false
    if ($done) { Receive-Job $job | Out-Null; $ok = ($LASTEXITCODE -eq 0) }
    else { Stop-Job $job }
    Remove-Job $job -Force
    return $ok
}

if (Test-DockerEngine) {
    Write-Host "Engine is already up; nothing to repair."
    & docker start postgres-local redis-local | Out-Null
    & docker ps --format '{{.Names}} - {{.Status}}'
    exit 0
}

Write-Host "Stopping Docker Desktop..."
Get-Process 'Docker Desktop', 'com.docker.backend' -ErrorAction SilentlyContinue |
    Stop-Process -Force
Start-Sleep -Seconds 4

# Every directory a Docker service binds a socket in. Clearing one and not the
# other simply moves the crash to the next service in the startup sequence.
$socketDirs = @(
    (Join-Path $env:LOCALAPPDATA 'Docker\run'),
    (Join-Path $env:LOCALAPPDATA 'docker-secrets-engine')
)

foreach ($dir in $socketDirs) {
    if (-not (Test-Path $dir)) { continue }
    $stamp = Get-Date -Format yyyyMMddHHmmssfff
    $leaf = "$(Split-Path $dir -Leaf).stale-$stamp"
    Write-Host "Moving stale sockets aside: $dir -> $leaf"
    try {
        Rename-Item -Path $dir -NewName $leaf -ErrorAction Stop
    } catch {
        Write-Warning "Could not rename $dir : $($_.Exception.Message)"
    }
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

$exe = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'
if (-not (Test-Path $exe)) {
    # Docker Desktop installs per-user here, not under Program Files.
    throw "Docker Desktop not found at $exe"
}
Write-Host "Starting Docker Desktop..."
Start-Process $exe

Write-Host "Waiting for the engine (up to $TimeoutMinutes minutes)..."
$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
while ((Get-Date) -lt $deadline) {
    if (Test-DockerEngine) {
        Write-Host "Engine is up. Starting containers..."
        & docker start postgres-local redis-local | Out-Null
        Start-Sleep -Seconds 2
        & docker ps --format '{{.Names}} - {{.Status}}'
        exit 0
    }
    Start-Sleep -Seconds 8
}

Write-Warning "The engine did not come up within $TimeoutMinutes minutes."
Write-Warning "Look for the next stale socket -- the path is named in the error:"
Write-Warning "  Select-String -Path `"$env:LOCALAPPDATA\Docker\log\host\com.docker.backend.exe.log`" -Pattern 'reporting error to user' | Select-Object -Last 1"
exit 1
