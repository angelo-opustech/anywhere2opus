[CmdletBinding()]
param(
    [string]$LauncherPath = "",
    [string]$RunKeyName = "anywhere2opus",
    [switch]$StartNow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($LauncherPath)) {
    $LauncherPath = Join-Path (Split-Path -Parent $PSCommandPath) "start-anywhere2opus-keepalive.ps1"
}

if (-not (Test-Path $LauncherPath)) {
    throw "Launcher script not found: $LauncherPath"
}

$runKeyPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$command = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$LauncherPath`""

New-Item -Path $runKeyPath -Force | Out-Null
Set-ItemProperty -Path $runKeyPath -Name $RunKeyName -Value $command

Write-Host "Autostart configured in $runKeyPath with name $RunKeyName"
Write-Host "Command: $command"

if ($StartNow) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $LauncherPath
}