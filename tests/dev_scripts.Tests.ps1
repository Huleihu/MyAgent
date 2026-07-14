# Verifies that local development scripts exist and PowerShell can parse them.

$projectRoot = Split-Path -Parent $PSScriptRoot
$scriptPaths = @(
    (Join-Path $projectRoot 'scripts/start-dev.ps1'),
    (Join-Path $projectRoot 'scripts/stop-dev.ps1')
)
$launcherPaths = @(
    (Join-Path $projectRoot 'start-dev.cmd'),
    (Join-Path $projectRoot 'stop-dev.cmd')
)
$stopScriptContent = Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'scripts/stop-dev.ps1')

Describe 'Development scripts' {
    foreach ($scriptPath in $scriptPaths) {
        It "exists: $scriptPath" {
            Test-Path -LiteralPath $scriptPath | Should Be $true
        }
    }

    foreach ($scriptPath in $scriptPaths) {
        It "parses: $scriptPath" {
            { [scriptblock]::Create((Get-Content -Raw -LiteralPath $scriptPath)) } |
                Should Not Throw
        }
    }

    foreach ($launcherPath in $launcherPaths) {
        It "exists: $launcherPath" {
            Test-Path -LiteralPath $launcherPath | Should Be $true
        }
    }

    It 'stops listeners without restricting the local address family' {
        $stopScriptContent | Should Not Match 'LocalAddress'
    }

    It 'continues when a listener process exits during shutdown' {
        $stopScriptContent | Should Match 'ProcessCommandException'
    }

    It 'stops children of an exited reload process' {
        $stopScriptContent | Should Match 'ParentProcessId'
    }
}
