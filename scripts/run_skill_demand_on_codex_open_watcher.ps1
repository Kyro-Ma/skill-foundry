param(
    [string]$WorkspaceRoot = "",
    [int]$PollSeconds = 10,
    [int]$MaxIdeas = 10,
    [int]$MaxWorkers = 10,
    [string]$CodexCli = "",
    [string]$CodexModel = "gpt-5.5",
    [string]$CodexReasoningEffort = "xhigh",
    [switch]$UsePythonRunner,
    [switch]$RunIfCodexAlreadyOpenAtWatcherStart
)

$ErrorActionPreference = "Continue"

if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
    $WorkspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
} else {
    $WorkspaceRoot = (Resolve-Path -LiteralPath $WorkspaceRoot).Path
}

$Runner = Join-Path $WorkspaceRoot "skill-demand-agent\scripts\run_skill_demand_agent.py"
$LogDir = Join-Path $WorkspaceRoot "logs"
$LogPath = Join-Path $LogDir "skill-demand-on-codex-open.log"
$PidPath = Join-Path $LogDir "skill-demand-on-codex-open.pid"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log([string]$message) {
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "$(Get-Date -Format o) $message"
}

function Get-PythonPath {
    $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundled) {
        return $bundled
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }
    throw "Python was not found."
}

function Get-CodexCliPath {
    if (-not [string]::IsNullOrWhiteSpace($CodexCli)) {
        if (Test-Path -LiteralPath $CodexCli) {
            return (Resolve-Path -LiteralPath $CodexCli).Path
        }
        throw "Codex CLI was not found at $CodexCli."
    }

    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_CLI_PATH) -and (Test-Path -LiteralPath $env:CODEX_CLI_PATH)) {
        return (Resolve-Path -LiteralPath $env:CODEX_CLI_PATH).Path
    }

    $configPath = Join-Path $env:USERPROFILE ".codex\config.toml"
    if (Test-Path -LiteralPath $configPath) {
        $configText = Get-Content -LiteralPath $configPath -Raw
        $match = [regex]::Match($configText, "CODEX_CLI_PATH\s*=\s*['""]([^'""]+)['""]")
        if ($match.Success -and (Test-Path -LiteralPath $match.Groups[1].Value)) {
            return (Resolve-Path -LiteralPath $match.Groups[1].Value).Path
        }
    }

    $localCodexRoot = Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin"
    if (Test-Path -LiteralPath $localCodexRoot) {
        $candidate = Get-ChildItem -LiteralPath $localCodexRoot -Recurse -File -Filter "codex.exe" |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }

    $command = Get-Command codex -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "Codex CLI was not found."
}

function Get-CodexMainProcess {
    Get-CimInstance Win32_Process -Filter "Name = 'Codex.exe'" |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -like "*\app\Codex.exe*" -and
            $_.CommandLine -notlike "*--type=*"
        }
}

function Get-CodexMainProcessKey {
    $process = @(Get-CodexMainProcess | Sort-Object CreationDate -Descending | Select-Object -First 1)
    if (-not $process -or @($process).Count -eq 0) {
        return ""
    }
    return "$($process[0].ProcessId)|$($process[0].CreationDate)"
}

function Test-SkillDemandAgentRunning {
    $matches = Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and
            (
                $_.CommandLine -like "*run_skill_demand_agent.py*" -or
                ($_.CommandLine -like "*codex.exe*" -and $_.CommandLine -like "*skill-demand-agent*")
            ) -and
            $_.ProcessId -ne $PID
        }
    return @($matches).Count -gt 0
}

function Invoke-SkillDemandAgentWithCodex {
    try {
        $codex = Get-CodexCliPath
    } catch {
        Write-Log "ERROR: $($_.Exception.Message)"
        return
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $codexLog = Join-Path $LogDir "skill-demand-on-codex-open-codex-$timestamp.log"
    $lastMessage = Join-Path $LogDir "skill-demand-on-codex-open-codex-$timestamp.last.md"
    $reasoningConfig = "model_reasoning_effort=`"$CodexReasoningEffort`""
    $prompt = @"
Use the local skill-demand-agent workflow once.

Working directory: $WorkspaceRoot
Skill instructions: read skill-demand-agent/SKILL.md before acting.

Run the full pipeline once with:
- max ideas: $MaxIdeas
- max workers: $MaxWorkers
- score threshold: 90
- min evidence: 3
- max search rounds: 3
- output root: $WorkspaceRoot

Do not start any background watcher or hourly loop.
Do not publish to ClawHub or GitHub from this open-triggered run.
When finished, report the run id, generated skills, and review pass count.
"@

    Write-Log "START: Codex opened; running skill-demand-agent through Codex CLI model=$CodexModel reasoning=$CodexReasoningEffort."
    Write-Log "CODEX_LOG: $codexLog"
    Push-Location $WorkspaceRoot
    try {
        $prompt | & $codex `
            -a never `
            -s danger-full-access `
            exec `
            -C $WorkspaceRoot `
            --skip-git-repo-check `
            -m $CodexModel `
            -c $reasoningConfig `
            -o $lastMessage `
            - 2>&1 |
            ForEach-Object {
                Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value $_.ToString()
                Add-Content -LiteralPath $codexLog -Encoding UTF8 -Value $_.ToString()
            }
        Write-Log "END: Codex CLI skill-demand-agent run exited with code $LASTEXITCODE. Last message: $lastMessage"
    } catch {
        Write-Log "ERROR: Codex CLI skill-demand-agent run failed: $($_.Exception.Message)"
    } finally {
        Pop-Location
    }
}

function Invoke-SkillDemandAgent {
    if (Test-SkillDemandAgentRunning) {
        Write-Log "SKIP: skill-demand-agent is already running."
        return
    }

    if (-not $UsePythonRunner) {
        Invoke-SkillDemandAgentWithCodex
        return
    }

    if (-not (Test-Path -LiteralPath $Runner)) {
        Write-Log "ERROR: runner not found at $Runner"
        return
    }

    try {
        $python = Get-PythonPath
    } catch {
        Write-Log "ERROR: $($_.Exception.Message)"
        return
    }

    Write-Log "START: Codex opened; running skill-demand-agent."
    Push-Location $WorkspaceRoot
    try {
        & $python $Runner `
            --max-ideas $MaxIdeas `
            --max-workers $MaxWorkers `
            --score-threshold 90 `
            --min-evidence 3 `
            --max-search-rounds 3 `
            --output-root $WorkspaceRoot 2>&1 |
            ForEach-Object {
                Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value $_.ToString()
            }
        Write-Log "END: skill-demand-agent exited with code $LASTEXITCODE."
    } catch {
        Write-Log "ERROR: skill-demand-agent failed: $($_.Exception.Message)"
    } finally {
        Pop-Location
    }
}

$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, "Global\SkillDemandAgentOnCodexOpenWatcher", [ref]$createdNew)
if (-not $createdNew) {
    Write-Log "Another skill-demand-agent Codex-open watcher is already running; exiting."
    exit 0
}

try {
    Set-Content -LiteralPath $PidPath -Encoding UTF8 -Value $PID
    $lastCodexProcessKey = Get-CodexMainProcessKey
    Write-Log "Watcher started. Codex running at startup: $(-not [string]::IsNullOrWhiteSpace($lastCodexProcessKey)). Process key: $lastCodexProcessKey."
    if ((-not [string]::IsNullOrWhiteSpace($lastCodexProcessKey)) -and $RunIfCodexAlreadyOpenAtWatcherStart) {
        Invoke-SkillDemandAgent
    }

    while ($true) {
        $currentCodexProcessKey = Get-CodexMainProcessKey
        if (
            (-not [string]::IsNullOrWhiteSpace($currentCodexProcessKey)) -and
            ($currentCodexProcessKey -ne $lastCodexProcessKey)
        ) {
            Write-Log "Codex open detected. Previous process key: $lastCodexProcessKey. Current process key: $currentCodexProcessKey."
            Invoke-SkillDemandAgent
        }
        $lastCodexProcessKey = $currentCodexProcessKey
        Start-Sleep -Seconds $PollSeconds
    }
} finally {
    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
