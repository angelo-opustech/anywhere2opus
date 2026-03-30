[CmdletBinding()]
param(
    [string]$Distro = "AlmaLinux-9",
    [string]$ServiceName = "anywhere2opus",
    [string]$HealthUrl = "http://localhost:8000/connectors",
    [int]$Attempts = 30,
    [int]$DelaySeconds = 2,
    [switch]$RestartService,
    [switch]$Stop
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-KeepaliveProcesses {
    $escapedDistro = [Regex]::Escape($Distro)

    @(Get-CimInstance Win32_Process -Filter "Name = 'wsl.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match "ANYWHERE2OPUS_KEEPALIVE=1" -and
        $_.CommandLine -match $escapedDistro
    })
}

function Invoke-Wsl {
    param(
        [string]$Command
    )

    & wsl.exe -d $Distro -- bash -lc $Command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL command failed for distro $Distro"
    }
}

function Wait-ForHealth {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing $HealthUrl -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                return [string]$response.StatusCode
            }
        }
        catch {
        }

        Start-Sleep -Seconds $DelaySeconds
    }

    throw "Application did not become reachable at $HealthUrl"
}

if ($Stop) {
    $processes = @(Get-KeepaliveProcesses)
    foreach ($process in $processes) {
        Stop-Process -Id $process.ProcessId -Force
    }

    Write-Host "Stopped keepalive processes: $($processes.Count)"
    exit 0
}

if ($RestartService) {
    Invoke-Wsl -Command "systemctl restart $ServiceName"
}

$processes = @(Get-KeepaliveProcesses)
if ($processes.Count -eq 0) {
    $linuxCommand = "export ANYWHERE2OPUS_KEEPALIVE=1; systemctl start $ServiceName; while true; do sleep 300; done"
    $startedProcess = Start-Process -FilePath "wsl.exe" -ArgumentList @("-d", $Distro, "--", "bash", "-lc", $linuxCommand) -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 2
    $processes = @($startedProcess)
}
else {
    Invoke-Wsl -Command "systemctl start $ServiceName"
}

$statusCode = Wait-ForHealth

Write-Host "Keepalive active for $Distro"
Write-Host "Processes: $($processes.Count)"
Write-Host "HTTP:      $statusCode"