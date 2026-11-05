# Installs dist\JungleSplits-Setup.exe silently into a temporary folder, checks the installed app (files,
# language file, uninstall entry, self-test, relaunch after a silent install), then uninstalls and checks
# nothing is left. Run by the release workflow on a clean GitHub runner.
#
# The installer reuses the folder of an existing installation with the same AppId, so on a machine that
# already has Jungle Splits installed this test would touch that installation: it refuses to run there.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$setup = Join-Path $root "dist\JungleSplits-Setup.exe"
$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{8F3C2A51-7B1E-4C55-9E2A-4D6B1F0A9C21}_is1"
if (Test-Path $key) { throw "Jungle Splits is installed on this machine; run this test on a clean machine (CI)." }
$dir = Join-Path ([IO.Path]::GetTempPath()) "jungle-splits-installer-test"

function Assert($condition, $message) {
    if (-not $condition) { throw "FAILED: $message" }
    Write-Host "ok   $message"
}

$p = Start-Process $setup -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LANG=brazilianportuguese /DIR=`"$dir`"" -PassThru
$p.WaitForExit()
Assert ($p.ExitCode -eq 0) "installer exit code 0"
Assert (Test-Path "$dir\JungleSplits.exe") "app installed"
Assert (Test-Path "$dir\unins000.exe") "uninstaller installed"
Assert ((Get-Content "$dir\install.ini" -Raw) -match "language=brazilianportuguese") "installer language saved for the app"
$entry = Get-ItemProperty $key
Assert ($entry.InstallLocation.TrimEnd("\") -eq $dir.TrimEnd("\")) "uninstall entry points to the install folder"

# A silent install is how the app updates itself: the installer must start the app again.
$relaunched = $null
for ($i = 0; $i -lt 30 -and -not $relaunched; $i++) {
    Start-Sleep -Milliseconds 500
    $relaunched = Get-Process JungleSplits -ErrorAction SilentlyContinue
}
Assert ($relaunched -ne $null) "app relaunched after a silent install"
$relaunched | Stop-Process -Force
Start-Sleep -Seconds 1

$report = Join-Path ([IO.Path]::GetTempPath()) "jungle-splits-selftest.txt"
$t = Start-Process "$dir\JungleSplits.exe" -ArgumentList "--self-test `"$report`"" -PassThru
$t.WaitForExit()
Get-Content $report | ForEach-Object { Write-Host "     $_" }
Assert ($t.ExitCode -eq 0) "installed app self-test"

$u = Start-Process "$dir\unins000.exe" -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" -PassThru
$u.WaitForExit()
Start-Sleep -Seconds 3
Assert (-not (Test-Path "$dir\JungleSplits.exe")) "uninstall removed the app"
Assert (-not (Test-Path $key)) "uninstall removed the uninstall entry"
Write-Host "installer test passed"
