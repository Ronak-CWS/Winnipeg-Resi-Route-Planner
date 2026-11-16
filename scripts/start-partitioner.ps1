param([int]$Port = 8765, [switch]$Restart)
$ErrorActionPreference = 'Stop'
$partitionRoot = Split-Path -Parent $PSScriptRoot
$partitionAudit = Join-Path $partitionRoot 'outputs\2026-11-04_monday_map\audit\partition_app'
New-Item -ItemType Directory -Force -Path $partitionAudit | Out-Null
$partitionPidFile = Join-Path $partitionAudit 'server.pid'
$partitionExpectedStorage = Join-Path $partitionRoot 'outputs\2026-11-04_monday_map'
$partitionExistingState = $null
try { $partitionExistingState = Invoke-RestMethod "http://127.0.0.1:$Port/api/state" -TimeoutSec 2 } catch {}
if ($partitionExistingState -and $partitionExistingState.version -like 'winnipeg-geography-*') {
    if ([IO.Path]::GetFullPath($partitionExistingState.storage) -ne [IO.Path]::GetFullPath($partitionExpectedStorage)) {
        throw 'This port serves a different workspace. Its process was not stopped.'
    }
    if (-not $Restart) {
        Set-Content -LiteralPath $partitionPidFile -Value $partitionExistingState.pid
        Write-Output "Monday partitioner is running: http://127.0.0.1:$Port"
        return
    }
    if (-not (Test-Path -LiteralPath $partitionPidFile) -or [int](Get-Content -LiteralPath $partitionPidFile) -ne $partitionExistingState.pid) {
        throw 'The server process differs from its local PID receipt. It was not stopped.'
    }
    Stop-Process -Id ([int]$partitionExistingState.pid)
}
$partitionListener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($partitionListener) {
    try {
        $partitionState = Invoke-RestMethod "http://127.0.0.1:$Port/api/state"
        if ($partitionState.version -like 'winnipeg-geography-*') {
            Write-Output "Monday partitioner is running: http://127.0.0.1:$Port"
            return
        }
    } catch {}
    throw "Port $Port is already in use by another application. Choose -Port explicitly."
}
$partitionVenvPython = Join-Path $partitionRoot '.venv\Scripts\python.exe'
$partitionPython = if (Test-Path -LiteralPath $partitionVenvPython) { $partitionVenvPython } else { (Get-Command python).Source }
$partitionProcess = Start-Process -FilePath $partitionPython -ArgumentList @('-u', '-m', 'partition_app.server', '--port', "$Port") -WorkingDirectory $partitionRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $partitionAudit 'server.stdout.log') -RedirectStandardError (Join-Path $partitionAudit 'server.stderr.log')
for ($partitionAttempt = 0; $partitionAttempt -lt 12; $partitionAttempt++) {
    Start-Sleep -Milliseconds 300
    try {
        $partitionReady = Invoke-RestMethod "http://127.0.0.1:$Port/api/state" -TimeoutSec 1
        if ($partitionReady.version -like 'winnipeg-geography-*' -and [IO.Path]::GetFullPath($partitionReady.storage) -eq [IO.Path]::GetFullPath($partitionExpectedStorage) -and (!$partitionExistingState -or $partitionReady.csrf -ne $partitionExistingState.csrf)) {
            # Windows' venv launcher can spawn the real Python as a child. Use
            # the verified server's PID, not the launcher process's PID.
            Set-Content -LiteralPath $partitionPidFile -Value $partitionReady.pid
            Write-Output "Monday partitioner started: http://127.0.0.1:$Port"
            Write-Output "Local process: $($partitionReady.pid)"
            return
        }
    } catch {}
}
throw 'The server did not become ready. Check audit/partition_app/server.stderr.log.'
