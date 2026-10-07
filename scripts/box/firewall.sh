#!/usr/bin/env bash
# Inside the container, as root, once: outgoing traffic only to the hosts in the allow list (resolved
# to addresses now, the way Anthropic's reference dev container does it), then the night runs as the
# unprivileged user `node`, who cannot change the rules.
#   firewall.sh -- <command...>
set -eu
[ "${1:-}" = -- ] && shift
hosts=$( { grep -hvE '^\s*(#|$)' /opt/nightcall/scripts/box/allow.txt "$PWD/box-allow.txt" 2>/dev/null || true
           printf '%s\n' ${NIGHTCALL_BOX_ALLOW:-}; } | sed 's/^\*\.//' | sort -u)
ipset create box-allow hash:net -exist
for h in $hosts; do
  for ip in $(dig +short A "$h" | grep -E '^[0-9.]+$'); do ipset add box-allow "$ip" -exist; done
done
iptables -F OUTPUT
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m set --match-set box-allow dst -j ACCEPT
iptables -P OUTPUT DROP
ip6tables -P OUTPUT DROP 2>/dev/null || true
echo "box: network open to $(ipset list box-allow | grep -cE '^[0-9]') addresses of $(echo "$hosts" | wc -w | tr -d ' ') hosts"
exec setpriv --reuid=node --regid=node --init-groups env HOME=/home/node "$@"
