@echo off
powershell.exe -NoProfile -WindowStyle Hidden -Command "& wsl.exe -d Ubuntu -u root -- systemctl start agentscope-scope-demo-api.service; if ($LASTEXITCODE -ne 0) { exit 1 }; Start-Process -FilePath 'http://127.0.0.1:18003/?view=scope-demo'"
