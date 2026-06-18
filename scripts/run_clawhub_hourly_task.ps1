$ErrorActionPreference = "Continue"

$WorkspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$LogDir = Join-Path $WorkspaceRoot "logs"
$LogPath = Join-Path $LogDir "clawhub-hourly-upload.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value ""
Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "===== $(Get-Date -Format o) ====="

try {
    & (Join-Path $PSScriptRoot "resume_clawhub_upload.ps1") -WorkspaceRoot $WorkspaceRoot -MaxAttempts 68 2>&1 |
        ForEach-Object {
            $line = $_.ToString()
            Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value $line
            Write-Output $line
        }
    exit 0
} catch {
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "UNHANDLED ERROR: $($_.Exception.Message)"
    exit 1
}
