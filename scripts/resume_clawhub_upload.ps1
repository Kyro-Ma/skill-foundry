param(
    [string]$WorkspaceRoot = "",
    [string]$ManifestPath = "",
    [string]$Version = "0.1.0",
    [string]$RenamedVersion = "0.1.1",
    [string]$Tags = "generated,skill-demand-agent",
    [int]$MaxAttempts = 68
)

$ErrorActionPreference = "Continue"

if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
    $WorkspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
} else {
    $WorkspaceRoot = (Resolve-Path -LiteralPath $WorkspaceRoot).Path
}

if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
    $ManifestPath = Join-Path $WorkspaceRoot "clawhub_upload_manifest.json"
}

function Save-Manifest($manifest, [string]$path) {
    $manifest.generated_at = (Get-Date).ToString("o")
    $manifest.total = @($manifest.skills).Count
    $manifest.uploaded = @($manifest.skills | Where-Object { $_.status -eq "uploaded" }).Count
    $manifest.blocked = @($manifest.skills | Where-Object { $_.status -eq "blocked" }).Count
    $manifest.pending = @($manifest.skills | Where-Object { ($_.status -ne "uploaded") -and ($_.status -ne "blocked") }).Count
    $manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $path -Encoding UTF8
}

function Get-SkillSlug([string]$skillPath) {
    $runId = Split-Path (Split-Path $skillPath -Parent) -Leaf
    $suffix = $runId.Substring($runId.Length - 6)
    $name = Split-Path $skillPath -Leaf
    $baseMax = 64 - $suffix.Length - 1
    if ($name.Length -gt $baseMax) {
        $base = $name.Substring(0, $baseMax).TrimEnd("-")
    } else {
        $base = $name
    }
    return "$base-$suffix"
}

function Get-SkillDisplayName([string]$skillPath) {
    $skillMd = Join-Path $skillPath "SKILL.md"
    if (Test-Path -LiteralPath $skillMd) {
        $heading = Select-String -LiteralPath $skillMd -Pattern "^#\s+(.+)$" -List
        if ($heading -and $heading.Matches.Count -gt 0) {
            return $heading.Matches[0].Groups[1].Value.Trim()
        }
    }
    $name = Split-Path $skillPath -Leaf
    return ((($name -split "-") | ForEach-Object {
        if ($_ -eq "api") { "API" }
        elseif ($_ -eq "ai") { "AI" }
        elseif ($_ -eq "llm") { "LLM" }
        elseif ($_ -eq "cpu") { "CPU" }
        elseif ($_ -eq "gpu") { "GPU" }
        elseif ($_ -eq "usa") { "USA" }
        elseif ($_ -eq "qemu") { "QEMU" }
        elseif ($_ -eq "toml") { "TOML" }
        elseif ($_ -eq "3d") { "3D" }
        else { (Get-Culture).TextInfo.ToTitleCase($_) }
    }) -join " ")
}

function New-Manifest([string]$workspaceRoot) {
    $skillRoot = Join-Path $workspaceRoot "generated_skills"
    $skills = Get-ChildItem -LiteralPath $skillRoot -Recurse -File -Filter "SKILL.md" |
        ForEach-Object { $_.Directory.FullName } |
        Sort-Object -Unique |
        ForEach-Object {
            $runId = Split-Path (Split-Path $_ -Parent) -Leaf
            [pscustomobject]@{
                skill = Split-Path $_ -Leaf
                run_id = $runId
                slug = Get-SkillSlug $_
                path = $_
                status = "pending"
                uploaded_at = ""
                last_attempt_at = ""
                last_error = ""
            }
        }
    return [pscustomobject]@{
        generated_at = (Get-Date).ToString("o")
        total = @($skills).Count
        uploaded = 0
        pending = @($skills).Count
        skills = @($skills)
    }
}

$clawhub = Get-Command clawhub -ErrorAction SilentlyContinue
if (-not $clawhub) {
    throw "clawhub CLI is not installed or not on PATH."
}

if (Test-Path -LiteralPath $ManifestPath) {
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
} else {
    $manifest = New-Manifest $WorkspaceRoot
}

$attempts = 0
$publishedThisRun = 0
$blocked = $false
$transientStop = $false

foreach ($entry in @($manifest.skills | Where-Object { ($_.status -ne "uploaded") -and ($_.status -ne "blocked") })) {
    if ($attempts -ge $MaxAttempts) {
        break
    }
    if (-not (Test-Path -LiteralPath $entry.path)) {
        $entry.status = "missing"
        $entry.last_attempt_at = (Get-Date).ToString("o")
        $entry.last_error = "Local skill path no longer exists."
        Save-Manifest $manifest $ManifestPath
        continue
    }

    $attempts++
    $entry.last_attempt_at = (Get-Date).ToString("o")

    $shouldRename = $entry.status -eq "rename_pending"
    if (($entry.status -eq "failed") -and (-not [string]::IsNullOrWhiteSpace($entry.old_slug)) -and ($entry.old_slug -ne $entry.slug)) {
        $shouldRename = $true
    }

    if ($shouldRename) {
        $oldSlug = $entry.old_slug
        if ([string]::IsNullOrWhiteSpace($oldSlug) -or $oldSlug -eq $entry.slug) {
            $entry.status = "pending_update"
            Save-Manifest $manifest $ManifestPath
        } else {
            $renameResult = & clawhub --no-input skill rename --yes $oldSlug $entry.slug 2>&1
            $renameText = $renameResult -join "`n"
            if ($LASTEXITCODE -eq 0) {
                $entry.status = "pending_update"
                $entry.last_error = ""
                Write-Output "RENAMED $oldSlug -> $($entry.slug)"
                Save-Manifest $manifest $ManifestPath
            } elseif ($renameText -match "already|exists|not found|404") {
                $entry.status = "pending_update"
                $entry.last_error = $renameText
                Write-Output "CHECK $($entry.slug): rename may already be complete; publishing update next."
                Save-Manifest $manifest $ManifestPath
            } elseif ($renameText -match "ECONN|ETIMEDOUT|ENOTFOUND|network|socket|fetch failed|timeout|temporarily unavailable|502|503|504|Checking token|not logged in|token|auth") {
                $entry.last_error = $renameText
                $transientStop = $true
                Write-Output "WAIT $oldSlug -> $($entry.slug): ClawHub/network/auth issue; will retry next run."
                Save-Manifest $manifest $ManifestPath
                break
            } else {
                $entry.status = "failed"
                $entry.last_error = $renameText
                Write-Output "FAILED rename $oldSlug -> $($entry.slug): $renameText"
                Save-Manifest $manifest $ManifestPath
                continue
            }
        }
    }

    $publishVersion = $Version
    if ($entry.status -eq "pending_update") {
        $publishVersion = $RenamedVersion
    }
    $displayName = Get-SkillDisplayName $entry.path
    $result = & clawhub --no-input skill publish $entry.path --slug $entry.slug --name $displayName --version $publishVersion --tags $Tags 2>&1
    $text = $result -join "`n"
    if ($LASTEXITCODE -eq 0) {
        $entry.status = "uploaded"
        $entry.uploaded_at = (Get-Date).ToString("o")
        $entry.last_error = ""
        $publishedThisRun++
        Write-Output "UPLOADED $($entry.slug)"
        Save-Manifest $manifest $ManifestPath
        Start-Sleep -Seconds 5
        continue
    }

    $entry.last_error = $text
    if ($text -match "Version\s+$([regex]::Escape($publishVersion))\s+already exists|Version .* already exists") {
        $retryVersion = "0.1.1"
        if ($publishVersion -eq "0.1.1") {
            $retryVersion = "0.1.2"
        }
        $retryResult = & clawhub --no-input skill publish $entry.path --slug $entry.slug --name $displayName --version $retryVersion --tags $Tags 2>&1
        $retryText = $retryResult -join "`n"
        if ($LASTEXITCODE -eq 0) {
            $entry.status = "uploaded"
            $entry.uploaded_at = (Get-Date).ToString("o")
            $entry.last_error = ""
            $publishedThisRun++
            Write-Output "UPLOADED $($entry.slug)@$retryVersion"
            Save-Manifest $manifest $ManifestPath
            Start-Sleep -Seconds 5
            continue
        }
        $entry.last_error = $retryText
        $text = $retryText
    }

    if ($text -match "repeated template spam|spam from this account|policy|abuse") {
        $entry.status = "blocked"
        Write-Output "BLOCKED_POLICY $($entry.slug): ClawHub rejected this upload as a policy/spam blocker."
        Save-Manifest $manifest $ManifestPath
        continue
    }

    if ($text -match "Rate limit|max 5 new skills per hour|Please wait") {
        if ($entry.status -ne "pending_update") {
            $entry.status = "pending"
        }
        $blocked = $true
        Write-Output "BLOCKED $($entry.slug): ClawHub rate limit reached."
        Save-Manifest $manifest $ManifestPath
        break
    }

    if ($text -match "ECONN|ETIMEDOUT|ENOTFOUND|network|socket|fetch failed|timeout|temporarily unavailable|502|503|504|Checking token|not logged in|token|auth") {
        $entry.status = "pending"
        $transientStop = $true
        Write-Output "WAIT $($entry.slug): ClawHub/network/auth issue; will retry next run."
        Save-Manifest $manifest $ManifestPath
        break
    }

    $entry.status = "failed"
    Write-Output "FAILED $($entry.slug): $text"
    Save-Manifest $manifest $ManifestPath
}

Save-Manifest $manifest $ManifestPath

if ($manifest.pending -eq 0) {
    if ($manifest.blocked -gt 0) {
        Write-Output "SKIP: no pending ClawHub uploads remain. Blocked entries: $($manifest.blocked)."
    } else {
        Write-Output "SKIP: all ClawHub skills are already uploaded."
    }
} elseif ($blocked) {
    Write-Output "STOP: ClawHub blocked more uploads this hour. Uploaded this run: $publishedThisRun. Pending: $($manifest.pending). Blocked: $($manifest.blocked)."
} elseif ($transientStop) {
    Write-Output "STOP: transient ClawHub/network issue. Uploaded this run: $publishedThisRun. Pending: $($manifest.pending). Blocked: $($manifest.blocked)."
} else {
    Write-Output "DONE: uploaded this run: $publishedThisRun. Pending: $($manifest.pending). Blocked: $($manifest.blocked)."
}
