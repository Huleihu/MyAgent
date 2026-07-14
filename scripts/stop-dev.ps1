# Stops only processes that listen on the configured local development ports.
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = 'Stop'

function Stop-ExitedReloadChildren {
    param(
        [int]$ParentProcessId,
        [int]$Port
    )

    $childProcesses = @(
        Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentProcessId" -ErrorAction Stop
    )
    foreach ($childProcess in $childProcesses) {
        try {
            Stop-Process -Id $childProcess.ProcessId -Force
            Write-Host "Stopped reload child $($childProcess.ProcessId) on port $Port"
        }
        catch [Microsoft.PowerShell.Commands.ProcessCommandException] {
            Write-Host "Reload child $($childProcess.ProcessId) on port $Port has already exited"
        }
    }
}

foreach ($port in @($BackendPort, $FrontendPort)) {
    $listeners = @(
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    )

    if ($listeners.Count -eq 0) {
        Write-Host "No development service is listening on port $port"
        continue
    }

    foreach ($listener in $listeners) {
        if ($PSCmdlet.ShouldProcess("process $($listener.OwningProcess) on port $port", 'Stop development server')) {
            try {
                Stop-Process -Id $listener.OwningProcess -Force
                Write-Host "Stopped process $($listener.OwningProcess) on port $port"
            }
            catch [Microsoft.PowerShell.Commands.ProcessCommandException] {
                Write-Host "Process $($listener.OwningProcess) on port $port has already exited"
                Stop-ExitedReloadChildren -ParentProcessId $listener.OwningProcess -Port $port
            }
        }
    }
}
