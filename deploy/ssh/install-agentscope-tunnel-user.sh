#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" -eq 0
staging=${1:?Provide staging directory containing the SSH config and public key}
test -f "$staging/90-agentscope-tunnel.conf"
test -f "$staging/id_ed25519_agentscope_tunnel.pub"
ssh-keygen -lf "$staging/id_ed25519_agentscope_tunnel.pub"
test "$(wc -l < "$staging/id_ed25519_agentscope_tunnel.pub")" -eq 1
grep -Eq '^ssh-ed25519 [A-Za-z0-9+/=]+( .*)?$' "$staging/id_ed25519_agentscope_tunnel.pub"
if getent passwd agentscope-tunnel >/dev/null; then
    echo 'Account already exists; inspect before changing it.' >&2
    exit 1
fi
test ! -e /etc/ssh/sshd_config.d/90-agentscope-tunnel.conf

useradd --create-home --shell /usr/sbin/nologin agentscope-tunnel
install -d -o root -g root -m 0755 /home/agentscope-tunnel
install -d -o root -g root -m 0755 /home/agentscope-tunnel/.ssh
# The unattended key grants no shell and only this one local forwarding target.
{ printf 'restrict,port-forwarding,command="/bin/false",permitopen="127.0.0.1:18003" '; cat "$staging/id_ed25519_agentscope_tunnel.pub"; } > "$staging/authorized_keys"
install -o root -g root -m 0644 "$staging/authorized_keys" /home/agentscope-tunnel/.ssh/authorized_keys
install -o root -g root -m 0644 "$staging/90-agentscope-tunnel.conf" /etc/ssh/sshd_config.d/90-agentscope-tunnel.conf
/usr/sbin/sshd -t
systemctl reload ssh.service
/usr/sbin/sshd -T -C user=agentscope-tunnel,host=localhost,addr=127.0.0.1 | grep -E '^(authenticationmethods|passwordauthentication|allowtcpforwarding|allowstreamlocalforwarding|permitopen|permitlisten|maxsessions|forcecommand) '
