[CmdletBinding()]
param(
    [string]$RepoPath = "",
    [string]$Distro = "AlmaLinux-9",
    [string]$WslRepoPath = "/home/projects/anywhere2opus",
    [string]$ServiceName = "anywhere2opus",
    [switch]$SkipServiceRestart,
    [switch]$ForceReset
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoPath)) {
    $RepoPath = Split-Path -Parent $PSCommandPath
}

function Invoke-Git {
    param(
        [string]$Path,
        [string[]]$Arguments
    )

    & git -C $Path @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed in ${Path}: git -C ${Path} $($Arguments -join ' ')"
    }
}

function Invoke-WslBash {
    param(
        [string]$Command
    )

    & wsl -d $Distro -- bash -lc $Command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL command failed in distro $Distro"
    }
}

function Get-GitPorcelain {
    param(
        [string]$Path
    )

    $output = & git -C $Path status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read git status in ${Path}"
    }
    return ,@($output | Where-Object { $_ -and $_.Trim() })
}

function New-BashCommand {
    param(
        [string[]]$Lines
    )

    return ($Lines -join "; ")
}

function Get-GitHead {
    param(
        [string]$Path,
        [string]$Ref = "HEAD"
    )

    $output = (& git -C $Path rev-parse $Ref).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $output) {
        throw "Failed to resolve git ref ${Ref} in ${Path}"
    }
    return $output
}

function Wait-ForWindowsHttp {
    param(
        [string]$Url,
        [int]$Attempts = 30,
        [int]$DelaySeconds = 1
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                return [string]$response.StatusCode
            }
        }
        catch {
        }

        Start-Sleep -Seconds $DelaySeconds
    }

    throw "Windows HTTP health check did not return 200 for $Url"
}

Write-Host "[1/5] Resolving repository state..."
if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
    throw "RepoPath is not a git repository: $RepoPath"
}

$originHead = (& git -C $RepoPath symbolic-ref refs/remotes/origin/HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $originHead) {
    throw "Could not resolve origin/HEAD from $RepoPath"
}

$defaultBranch = $originHead -replace "^refs/remotes/origin/", ""
$targetRef = "origin/$defaultBranch"

Invoke-Git -Path $RepoPath -Arguments @("fetch", "origin")
$targetCommit = Get-GitHead -Path $RepoPath -Ref $targetRef

$windowsStatus = Get-GitPorcelain -Path $RepoPath
if (@($windowsStatus).Count -gt 0 -and -not $ForceReset) {
    throw "Windows clone has local changes. Commit/push first or rerun with -ForceReset."
}

$escapedWslRepoPath = $WslRepoPath.Replace("'", "'\''")
$wslStatusCommand = New-BashCommand -Lines @(
    "set -e",
    "cd '$escapedWslRepoPath'",
    "git status --porcelain"
)
$wslStatus = (& wsl -d $Distro -- bash -lc $wslStatusCommand)
if ($LASTEXITCODE -ne 0) {
    throw "Failed to read git status in ${Distro}:${WslRepoPath}"
}

$wslStatusLines = @($wslStatus | Where-Object { $_ -and $_.Trim() })
$wslHasChanges = @($wslStatusLines).Count -gt 0
if (@($wslStatusLines).Count -gt 0 -and -not $ForceReset) {
    throw "WSL clone has local changes. Commit/push first or rerun with -ForceReset."
}

$wslHeadCommand = New-BashCommand -Lines @(
    "set -e",
    "cd '$escapedWslRepoPath'",
    "git rev-parse HEAD"
)
$wslHeadBefore = (& wsl -d $Distro -- bash -lc $wslHeadCommand).Trim()
if ($LASTEXITCODE -ne 0 -or -not $wslHeadBefore) {
    throw "Failed to resolve WSL HEAD in ${Distro}:${WslRepoPath}"
}

Write-Host "[2/5] Aligning Windows clone to $targetRef..."
Invoke-Git -Path $RepoPath -Arguments @("config", "core.autocrlf", "false")
Invoke-Git -Path $RepoPath -Arguments @("checkout", $defaultBranch)
Invoke-Git -Path $RepoPath -Arguments @("reset", "--hard", $targetRef)
Invoke-Git -Path $RepoPath -Arguments @("clean", "-fd")

Write-Host "[3/5] Aligning AlmaLinux clone to $targetRef..."
$syncCommand = New-BashCommand -Lines @(
    "set -e",
    "cd '$escapedWslRepoPath'",
    "git fetch origin",
    "git checkout $defaultBranch",
    "git reset --hard $targetRef",
    "git clean -fd"
)
Invoke-WslBash -Command $syncCommand

$wslHeadAfter = (& wsl -d $Distro -- bash -lc $wslHeadCommand).Trim()
if ($LASTEXITCODE -ne 0 -or -not $wslHeadAfter) {
    throw "Failed to resolve updated WSL HEAD in ${Distro}:${WslRepoPath}"
}

if ($wslHeadAfter -ne $targetCommit) {
    throw "WSL clone did not land on expected commit $targetCommit"
}

$shouldRestartService = -not $SkipServiceRestart -and ($wslHasChanges -or $wslHeadBefore -ne $targetCommit)

if ($shouldRestartService) {
    Write-Host "[4/5] Restarting $ServiceName service in $Distro..."
    $serviceCommand = New-BashCommand -Lines @(
        "set -e",
        "systemctl restart $ServiceName",
        "for attempt in $(seq 1 30); do",
        "  systemctl is-active --quiet $ServiceName || exit 1",
        "  curl -fsS http://127.0.0.1:8000/connectors >/dev/null && exit 0",
        "  sleep 1",
        "done",
        "exit 1"
    )
    Invoke-WslBash -Command $serviceCommand
}
elseif ($SkipServiceRestart) {
    Write-Host "[4/5] Skipping service restart by request."
}
else {
    Write-Host "[4/5] Skipping service restart because the deployed commit is unchanged."
}

Write-Host "[5/5] Verifying HTTP health..."
$healthCommand = "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/connectors"
$statusCode = (& wsl -d $Distro -- bash -lc $healthCommand).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Health check command failed in distro $Distro"
}

if ($statusCode -ne "200") {
    throw "Unexpected HTTP status from application: $statusCode"
}

$windowsStatusCode = Wait-ForWindowsHttp -Url "http://localhost:8000/connectors"

$currentCommit = (& git -C $RepoPath rev-parse --short HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Failed to resolve current commit in $RepoPath"
}

Write-Host "Sync complete."
Write-Host "Branch: $defaultBranch"
Write-Host "Commit: $currentCommit"
Write-Host "WSL:    $statusCode"
Write-Host "Windows:$windowsStatusCode"