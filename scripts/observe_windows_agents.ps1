# Local, read-only Agent discovery for the independent 18003 demo.
param([switch]$Once)
$ErrorActionPreference='Stop'
while ($true) {
    try {
        $rows=@(Get-CimInstance Win32_Process -Filter "Name='Codex.exe' OR Name='Hermes.exe'" | ForEach-Object {
            $exe=$_.ExecutablePath
            if ($_.CommandLine -match '(?:^|\s)--type=') { return }
            if ($exe -and (($exe -match '\\OpenAI\.Codex_[^\\]+\\.*Codex\.exe$') -or ($exe -match '\\Programs\\Codex\\Codex\.exe$'))) {
                @{name='Codex 桌面实例';agent_type='codex';pid=[int]$_.ProcessId;started_at=$_.CreationDate.ToUniversalTime().ToString('yyyyMMddHHmmssfff');executable=$exe}
            } elseif ($exe -and (($exe -match '\\AppData\\Local\\OpenAI\\Codex\\bin\\[a-f0-9]+\\codex\.exe$') -or ($exe -match '\\\.vscode\\extensions\\openai\.chatgpt-[^\\]+\\bin\\windows-x86_64\\codex\.exe$'))) {
                @{name=('Codex 本机进程 '+$_.ProcessId);agent_type='codex';pid=[int]$_.ProcessId;started_at=$_.CreationDate.ToUniversalTime().ToString('yyyyMMddHHmmssfff');executable=$exe}
            } elseif ($exe -and $exe -match '\\Programs\\Hermes[^\\]*\\Hermes\.exe$') {
                @{name='Hermes 桌面实例';agent_type='hermes-desktop';pid=[int]$_.ProcessId;started_at=$_.CreationDate.ToUniversalTime().ToString('yyyyMMddHHmmssfff');executable=$exe}
            }
        })
        $body=@{rows=$rows}|ConvertTo-Json -Depth 4 -Compress
        $null=Invoke-RestMethod -Uri 'http://127.0.0.1:18003/api/agent-discovery/windows' -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 2
    } catch { if ($Once) { throw } }
    if ($Once) { break }
    Start-Sleep -Seconds 3
}
