param(
    [string]$Server = '8.163.125.168',
    [string]$User = 'agentscope-tunnel',
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\id_ed25519_agentscope_tunnel",
    [string]$KnownHostsFile = "$env:USERPROFILE\.ssh\known_hosts_agentscope_tunnel",
    [string]$LogDirectory = "$env:USERPROFILE\.agentscope\tunnel\logs"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ssh = "$env:WINDIR\System32\OpenSSH\ssh.exe"
foreach ($path in @($ssh, $IdentityFile, $KnownHostsFile)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file is missing: $path" }
}
$null = New-Item -ItemType Directory -Force -Path $LogDirectory
$logPath = Join-Path $LogDirectory 'tunnel.log'

function Write-TunnelLog([string]$Message) {
    # Retain one bounded previous log. No credentials or SSH debug output.
    if ((Test-Path -LiteralPath $logPath) -and (Get-Item -LiteralPath $logPath).Length -gt 524288) {
        $previous = "$logPath.1"
        if (Test-Path -LiteralPath $previous) { Remove-Item -LiteralPath $previous -Force }
        Move-Item -LiteralPath $logPath -Destination $previous
    }
    Add-Content -LiteralPath $logPath -Encoding UTF8 -Value ("{0:o} {1}" -f (Get-Date), $Message)
}

function Quote-Argument([string]$Value) {
    # These arguments never contain embedded quotes or trailing backslashes.
    if ($Value -match '["\r\n]' -or $Value.EndsWith('\')) { throw 'Invalid SSH argument' }
    return '"' + $Value + '"'
}

# Task Scheduler can terminate PowerShell without running its finally block.
# A non-inheritable job handle closes on supervisor exit and kills its SSH child.
if (-not ('AgentScopeTunnelJob' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
public sealed class AgentScopeTunnelJob : IDisposable {
    [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
        public long ProcessTime, JobTime;
        public uint Flags;
        public UIntPtr MinimumWorkingSet, MaximumWorkingSet;
        public uint ActiveProcesses;
        public UIntPtr Affinity;
        public uint Priority, Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] struct IoCounters {
        public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes;
    }
    [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {
        public BasicLimits Basic;
        public IoCounters Io;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool SetInformationJobObject(IntPtr job, int kind, ref ExtendedLimits value, uint length);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    IntPtr handle;
    public AgentScopeTunnelJob() {
        handle = CreateJobObject(IntPtr.Zero, null);
        if (handle == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        var limits = new ExtendedLimits();
        limits.Basic.Flags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if (!SetInformationJobObject(handle, 9, ref limits, (uint)Marshal.SizeOf(typeof(ExtendedLimits)))) {
            int error = Marshal.GetLastWin32Error();
            Dispose();
            throw new Win32Exception(error);
        }
    }
    public void Attach(Process process) {
        if (!AssignProcessToJobObject(handle, process.Handle)) throw new Win32Exception(Marshal.GetLastWin32Error());
    }
    public void Dispose() {
        if (handle != IntPtr.Zero) { CloseHandle(handle); handle = IntPtr.Zero; }
    }
}
'@
}

$mutex = New-Object System.Threading.Mutex($false, 'Local\AgentScope.SshTunnel.18030')
$ownsMutex = $false
$child = $null
$job = $null
try {
    try { $ownsMutex = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (-not $ownsMutex) { exit 0 }
    Write-TunnelLog 'Supervisor started; forwarding 127.0.0.1:18030 to server 127.0.0.1:18003.'
    $job = New-Object AgentScopeTunnelJob
    $failures = 0
    while ($true) {
        $started = Get-Date
        try {
            $arguments = @(
                '-F', 'NUL', '-N', '-T', '-i', $IdentityFile,
                '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none',
                '-o', 'PasswordAuthentication=no', '-o', 'KbdInteractiveAuthentication=no',
                '-o', 'StrictHostKeyChecking=yes', '-o', "UserKnownHostsFile=$KnownHostsFile",
                '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=10', '-o', 'ConnectionAttempts=1',
                '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
                '-L', '127.0.0.1:18030:127.0.0.1:18003', "$User@$Server"
            )
            $child = New-Object System.Diagnostics.Process
            $child.StartInfo.FileName = $ssh
            $child.StartInfo.Arguments = ($arguments | ForEach-Object { Quote-Argument $_ }) -join ' '
            $child.StartInfo.UseShellExecute = $false
            $child.StartInfo.CreateNoWindow = $true
            $child.StartInfo.RedirectStandardError = $true
            $null = $child.Start()
            $job.Attach($child)
            $errors = $child.StandardError.ReadToEndAsync()
            $reported = $false
            while (-not $child.WaitForExit(1000)) {
                if (-not $reported) {
                    $listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 18030 -State Listen -ErrorAction SilentlyContinue |
                        Where-Object { $_.OwningProcess -eq $child.Id }
                    if ($listener) {
                        Write-TunnelLog "SSH listener is ready; PID=$($child.Id)."
                        $reported = $true
                    }
                }
            }
            $detail = $errors.GetAwaiter().GetResult().Trim()
            if ($detail.Length -gt 2000) { $detail = $detail.Substring(0, 2000) }
            Write-TunnelLog "SSH exited; code=$($child.ExitCode); $detail"
        } catch {
            Write-TunnelLog "Tunnel attempt failed: $($_.Exception.Message)"
        } finally {
            if ($null -ne $child) {
                if (-not $child.HasExited) { $child.Kill(); $child.WaitForExit() }
                $child.Dispose()
                $child = $null
            }
        }
        if (((Get-Date) - $started).TotalSeconds -ge 60) { $failures = 0 }
        $failures++
        $delay = [Math]::Min(30, $failures * 5)
        Write-TunnelLog "Retrying in $delay seconds."
        Start-Sleep -Seconds $delay
    }
} finally {
    if ($null -ne $child) {
        if (-not $child.HasExited) { $child.Kill() }
        $child.Dispose()
    }
    if ($null -ne $job) { $job.Dispose() }
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
