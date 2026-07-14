# Starts local development services without modifying system settings.
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$PythonExecutable,
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 3000,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$frontendDirectory = Join-Path $projectRoot 'frontend'

function Test-ListeningPort {
    param([int]$Port)

    return $null -ne (
        Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
    )
}

function Resolve-PythonExecutable {
    param([string]$ConfiguredExecutable)

    if ($ConfiguredExecutable) {
        return $ConfiguredExecutable
    }

    if ($env:MYAGENT_PYTHON) {
        return $env:MYAGENT_PYTHON
    }

    $condaCommand = Get-Command 'conda' -ErrorAction SilentlyContinue
    if ($null -ne $condaCommand) {
        try {
            $environmentInfo = (& $condaCommand.Source env list --json | ConvertFrom-Json)
            $environmentPath = @(
                $environmentInfo.envs |
                    Where-Object { (Split-Path -Leaf $_) -eq 'myagent-py311' } |
                    Select-Object -First 1
            )
            if ($environmentPath.Count -eq 1) {
                $condaPython = Join-Path $environmentPath[0] 'python.exe'
                if (Test-Path -LiteralPath $condaPython -PathType Leaf) {
                    return $condaPython
                }
            }
        }
        catch {
            Write-Warning 'Unable to locate the myagent-py311 Conda environment; using python from PATH.'
        }
    }

    return 'python'
}

$resolvedPythonExecutable = Resolve-PythonExecutable -ConfiguredExecutable $PythonExecutable

# Clear proxies only for this script process and its child processes.
foreach ($proxyVariable in @('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')) {
    Remove-Item -LiteralPath "Env:$proxyVariable" -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $frontendDirectory -PathType Container)) {
    throw "Frontend directory does not exist: $frontendDirectory"
}

if (Test-ListeningPort -Port $BackendPort) {
    Write-Host "Backend is already listening on http://127.0.0.1:$BackendPort"
}
elseif ($PSCmdlet.ShouldProcess("backend port $BackendPort", 'Start development server')) {
    $backendStartParameters = @{
        FilePath = $resolvedPythonExecutable
        ArgumentList = @('-m', 'uvicorn', 'my_agent.web.app:app', '--reload', '--host', '127.0.0.1', '--port', $BackendPort)
        WorkingDirectory = $projectRoot
        WindowStyle = 'Hidden'
        RedirectStandardOutput = (Join-Path $projectRoot '.backend-dev.log')
        RedirectStandardError = (Join-Path $projectRoot '.backend-dev-error.log')
    }
    Start-Process @backendStartParameters
    Write-Host "Backend started on http://127.0.0.1:$BackendPort"
}

if (Test-ListeningPort -Port $FrontendPort) {
    Write-Host "Frontend is already listening on http://localhost:$FrontendPort"
}
elseif ($PSCmdlet.ShouldProcess("frontend port $FrontendPort", 'Start development server')) {
    $frontendStartParameters = @{
        FilePath = 'npm.cmd'
        ArgumentList = @('run', 'dev', '--', '--port', $FrontendPort)
        WorkingDirectory = $frontendDirectory
        WindowStyle = 'Hidden'
        RedirectStandardOutput = (Join-Path $frontendDirectory '.frontend-dev.log')
        RedirectStandardError = (Join-Path $frontendDirectory '.frontend-dev-error.log')
    }
    Start-Process @frontendStartParameters
    Write-Host "Frontend started on http://localhost:$FrontendPort"
}

if (-not $NoBrowser -and $PSCmdlet.ShouldProcess("http://localhost:$FrontendPort", 'Open browser')) {
    Start-Process "http://localhost:$FrontendPort"
}
