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
    return @($output | Where-Object { $_ -and $_.Trim() })
}

function New-BashCommand {
    param(
        [string[]]$Lines
    )

    return ($Lines -join "; ")
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

$windowsStatus = Get-GitPorcelain -Path $RepoPath
if ($windowsStatus.Count -gt 0 -and -not $ForceReset) {
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
if ($wslStatusLines.Count -gt 0 -and -not $ForceReset) {
    throw "WSL clone has local changes. Commit/push first or rerun with -ForceReset."
}

Write-Host "[2/5] Aligning Windows clone to $targetRef..."
Invoke-Git -Path $RepoPath -Arguments @("fetch", "origin")
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

if (-not $SkipServiceRestart) {
    Write-Host "[4/5] Restarting $ServiceName service in $Distro..."
    $serviceCommand = New-BashCommand -Lines @(
        "set -e",
        "systemctl restart $ServiceName",
        "sleep 3",
        "systemctl is-active --quiet $ServiceName"
    )
    Invoke-WslBash -Command $serviceCommand
}
else {
    Write-Host "[4/5] Skipping service restart."
}

Write-Host "[5/5] Verifying HTTP health..."
$healthCommand = "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/connectors"
$statusCode = (& wsl -d $Distro -- bash -lc $healthCommand).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Health check command failed in distro $Distro"
}

if ($statusCode -ne "200") {
    throw "Unexpected HTTP status from application: $statusCode"
}

$currentCommit = (& git -C $RepoPath rev-parse --short HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Failed to resolve current commit in $RepoPath"
}

Write-Host "Sync complete."
Write-Host "Branch: $defaultBranch"
Write-Host "Commit: $currentCommit"
Write-Host "HTTP:   $statusCode"