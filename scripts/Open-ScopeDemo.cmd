@echo off
powershell.exe -NoProfile -WindowStyle Hidden -Command "$scopeEntryRaw = & wsl.exe -d Ubuntu -u root -- /opt/agentscope/.venv/bin/python /opt/agentscope-history-v1/scripts/scope_browser_ticket.py; if ($LASTEXITCODE -ne 0) { exit 1 }; $scopeEntry = $scopeEntryRaw | ConvertFrom-Json; Start-Process -FilePath $scopeEntry.url"
