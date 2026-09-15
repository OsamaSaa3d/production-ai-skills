<#
Install the skills in this repo into an agent's skills directory.

The Windows half of scripts/install.sh, which needs WSL or Git Bash to run here
and so is not a real option for this repo's own author. Same flags, same output,
same rule: only directories holding a SKILL.md are copied, discovered by glob so
the list cannot go stale.

Usage:  .\scripts\install.ps1 --target <agent> [--user|--project] [--dry-run]
        .\scripts\install.ps1 --target <agent> --dest DIR
        .\scripts\install.ps1 --list
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

$Target = ''
$Scope = 'user'
$Dest = ''
$DryRun = $false
$List = $false

function Show-Usage {
    @'
Install the Production AI Skills into an agent's skills directory.

Usage:
  .\scripts\install.ps1 --target <agent> [--user|--project] [--dry-run]
  .\scripts\install.ps1 --target <agent> --dest DIR [--dry-run]
  .\scripts\install.ps1 --list

Options:
  --target <agent>  claude-code | codex | cursor | opencode | copilot | agents
  --user            Install for your user, across all projects (default).
  --project         Install into the current directory's project config.
  --dest DIR        Copy into DIR instead of a resolved agent path.
  --list            Print the resolved destination for every target and exit.
  --dry-run         Print what would be copied without copying it.
  -h, --help        This text.

Destinations (verified against vendor docs, 2026):
  claude-code  user ~/.claude/skills            project .\.claude\skills
  codex        user ~/.agents/skills            project .\.agents\skills
               (~/.codex/skills is still scanned but is the deprecated path)
  cursor       user ~/.cursor/skills            project .\.cursor\skills
  opencode     user ~/.config/opencode/skills   project .\.opencode\skills
               (opencode also discovers the singular 'skill/' directory as of
                its v2 release, so ~/.config/opencode/skills is the preferred,
                and current, path - verify against opencode's docs if it changes)
  copilot      user ~/.copilot/skills           project .\.github\skills
  agents       user ~/.agents/skills            project .\.agents\skills
               (cross-agent convention read by Codex, Cursor, opencode and
                Copilot; Claude Code does not read it)

Project scope installs into the current working directory, not into this repo.
'@ | Write-Output
}

function Resolve-Destination([string]$target, [string]$scope) {
    $home_dir = $HOME
    $config_home = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $home_dir '.config' }
    $project = (Get-Location).Path
    $map = @{
        'claude-code' = @{ user = Join-Path $home_dir '.claude\skills';   project = Join-Path $project '.claude\skills' }
        'codex'       = @{ user = Join-Path $home_dir '.agents\skills';   project = Join-Path $project '.agents\skills' }
        'cursor'      = @{ user = Join-Path $home_dir '.cursor\skills';   project = Join-Path $project '.cursor\skills' }
        'opencode'    = @{ user = Join-Path $config_home 'opencode\skills'; project = Join-Path $project '.opencode\skills' }
        'copilot'     = @{ user = Join-Path $home_dir '.copilot\skills';  project = Join-Path $project '.github\skills' }
        'agents'      = @{ user = Join-Path $home_dir '.agents\skills';   project = Join-Path $project '.agents\skills' }
    }
    if (-not $map.ContainsKey($target)) {
        Write-Output "install.ps1: unknown target '$target'"
        exit 2
    }
    return $map[$target][$scope]
}

function Get-Skills {
    Get-ChildItem -Path $Root -Directory |
        Where-Object { -not $_.Name.StartsWith('.') } |
        Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') } |
        Sort-Object Name
}

# Parsed by hand rather than with param(): the flags have to read the same as
# install.sh's so the README can document one set of commands.
$i = 0
while ($i -lt $args.Count) {
    $arg = [string]$args[$i]
    switch -Regex ($arg) {
        '^--target=' { $Target = $arg.Split('=', 2)[1]; $i++; break }
        '^--dest='   { $Dest = $arg.Split('=', 2)[1]; $i++; break }
        '^(--target|-Target)$' {
            if ($i + 1 -ge $args.Count) { Write-Output 'install.ps1: --target needs a value'; exit 2 }
            $Target = [string]$args[$i + 1]; $i += 2; break
        }
        '^(--dest|-Dest)$' {
            if ($i + 1 -ge $args.Count) { Write-Output 'install.ps1: --dest needs a value'; exit 2 }
            $Dest = [string]$args[$i + 1]; $i += 2; break
        }
        '^(--user|-User)$'       { $Scope = 'user'; $i++; break }
        '^(--project|-Project)$' { $Scope = 'project'; $i++; break }
        '^(--dry-run|-DryRun)$'  { $DryRun = $true; $i++; break }
        '^(--list|-List)$'       { $List = $true; $i++; break }
        '^(-h|--help|-Help)$'    { Show-Usage; exit 0 }
        default {
            Write-Output "install.ps1: unknown argument '$arg'"
            Show-Usage
            exit 2
        }
    }
}

$skills = @(Get-Skills)
if ($skills.Count -eq 0) {
    Write-Output "install.ps1: no skills found - expected <skill-name>\SKILL.md under $Root"
    exit 1
}

if ($List) {
    Write-Output "source: $Root ($($skills.Count) skills)"
    foreach ($s in $skills) { Write-Output "  $($s.Name)" }
    Write-Output ''
    Write-Output 'destinations:'
    foreach ($t in @('claude-code', 'codex', 'cursor', 'opencode', 'copilot', 'agents')) {
        Write-Output ("  {0,-12} user     {1}" -f $t, (Resolve-Destination $t 'user'))
        Write-Output ("  {0,-12} project  {1}" -f $t, (Resolve-Destination $t 'project'))
    }
    exit 0
}

if (-not $Target -and -not $Dest) {
    Write-Output 'install.ps1: --target is required (or --dest DIR)'
    Write-Output ''
    Show-Usage
    exit 2
}

$destination = if ($Dest) { $Dest } else { Resolve-Destination $Target $Scope }

Write-Output "installing $($skills.Count) skills"
Write-Output "  from  $Root"
Write-Output "  into  $destination"
if ($DryRun) { Write-Output '  (dry run - nothing will be written)' }
Write-Output ''

if (-not $DryRun -and -not (Test-Path $destination)) {
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
}

foreach ($s in $skills) {
    $into = Join-Path $destination $s.Name
    $action = if (Test-Path $into) { 'replace' } else { 'copy   ' }
    Write-Output "  $action $($s.Name)/"
    if (-not $DryRun) {
        if (Test-Path $into) { Remove-Item -Recurse -Force $into }
        Copy-Item -Recurse -Path $s.FullName -Destination $into
    }
}

Write-Output ''
if ($DryRun) {
    Write-Output 'dry run complete - no files written'
} else {
    Write-Output "installed $($skills.Count) skills into $destination"
}
exit 0
