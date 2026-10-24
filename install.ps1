<# Install Flashback Clips from PyPI with uv, then run `flashback-clips setup`. No elevation required. #>
[CmdletBinding()]
param(
    # PyPI requirement, or a local wheel path to test a build before it is published.
    [string]$Package = 'flashback-ai-toolkit',
    [ValidateSet('auto', 'codex', 'claude', 'both')]
    [string]$Agent = 'auto',
    [string]$SkillDir,
    [switch]$SkipSkill,
    [switch]$NoDependencyInstall,
    [switch]$NoPathUpdate
)
$ErrorActionPreference = 'Stop'

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE). Fix the error above and rerun the installer." }
}
function Find-Uv {
    $command = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    # A fresh WinGet or uv install is not on this process's PATH yet.
    foreach ($path in @((Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\uv.exe'), (Join-Path $HOME '.local\bin\uv.exe'))) {
        if (Test-Path -LiteralPath $path) { return $path }
    }
    return $null
}

try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows is required.' }
    Write-Host 'Flashback Clips setup: uv, the flashback-clips command, FFmpeg and the agent skill (Codex / Claude Code).'
    Write-Host 'Which Minecraft installation to use is asked later, the first time your agent needs the game.'
    $uv = Find-Uv
    if (-not $uv) {
        if ($NoDependencyInstall) { throw 'uv is missing. Install it (https://docs.astral.sh/uv/) or rerun without -NoDependencyInstall.' }
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
            throw 'WinGet is missing. Install uv from https://docs.astral.sh/uv/ and rerun.'
        }
        Write-Host 'Installing uv for the current user...'
        Invoke-Checked 'winget.exe' @('install', '--id', 'astral-sh.uv', '--exact', '--source', 'winget', '--scope', 'user', '--silent', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity')
        $uv = Find-Uv
        if (-not $uv) { throw 'uv was installed but not found. Reopen the terminal and rerun.' }
    }
    # uv supplies a private Python 3.11+ when needed; the system Python is not changed.
    $installArgs = @('tool', 'install', '--upgrade', $Package)
    if (Test-Path -LiteralPath $Package) { $installArgs += '--reinstall' }
    Invoke-Checked $uv $installArgs
    if (-not $NoPathUpdate) { Invoke-Checked $uv @('tool', 'update-shell') }
    $command = Join-Path ([string](& $uv tool dir --bin)).Trim() 'flashback-clips.exe'
    $setupArgs = @('setup', '--agent', $Agent)
    if ($SkillDir) { $setupArgs += @('--skill-dir', $SkillDir) }
    if ($SkipSkill) { $setupArgs += '--skip-skill' }
    if ($NoDependencyInstall) { $setupArgs += '--no-dependency-install' }
    Invoke-Checked $command $setupArgs
    Write-Host 'Installed. Reopen your terminal and agent (Codex / Claude Code), then ask it for a video.'
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
