#!/bin/bash
# State snapshot, run by `docker exec` as root: regular files under the watched roots with mode/uid/size/sha256,
# directories, and the server config. Volatile server logs are reported by path only.
for p in /home/user /tmp /etc /var/log /opt/fixture; do
  find "$p" -xdev \( -path '/home/user/.claude-server-commander/*.log' -o -path '/home/user/.claude-server-commander/*.txt' \) -prune -o \( -type f -printf 'F\t%p\t%m\t%u\t%s\t' -exec sha256sum {} \; \) -o \( -type d -printf 'D\t%p\t%m\t%u\n' \) -o \( -type l -printf 'L\t%p\t%l\n' \) 2>/dev/null
done
echo "CONFIG_BEGIN"; cat /home/user/.claude-server-commander/config.json 2>/dev/null; echo; echo "CONFIG_END"
