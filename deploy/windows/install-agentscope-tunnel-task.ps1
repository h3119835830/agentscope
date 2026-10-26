param(
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\id_ed25519_agentscope_tunnel",
    [string]$KnownHostsFile = "$env:USERPROFILE\.ssh\known_hosts_agentscope_tunnel"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$taskName = 'AgentScope SSH Tunnel'
# Keep task files outside packaged-app AppData virtualization. Task Scheduler
# must see the same physical path as the installing desktop process.
$installDirectory = Join-Path $env:USERPROFILE '.agentscope\tunnel'
$source = Join-Path $PSScriptRoot 'agentscope-tunnel.ps1'
$destination = Join-Path $installDirectory 'agentscope-tunnel.ps1'
foreach ($path in @($source, $IdentityFile, $KnownHostsFile)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file is missing: $path" }
    if ($path -match '["\r\n]') { throw 'Invalid file path' }
}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw "Task already exists; inspect it before updating: $taskName"
}
$null = New-Item -ItemType Directory -Force -Path $installDirectory
Copy-Item -LiteralPath $source -Destination $destination
$account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$actionArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -IdentityFile "{1}" -KnownHostsFile "{2}"' -f $destination, $IdentityFile, $KnownHostsFile
$action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument $actionArguments -WorkingDirectory $installDirectory
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$null = Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Private AgentScope SSH tunnel. Starts at user logon; reconnects without passwords; listens only on 127.0.0.1:18030.'
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
