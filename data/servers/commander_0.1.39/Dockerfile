FROM node:24.17.0-bookworm-slim
# desktop-commander 0.1.39 (npm tarball pinned by sha256 in SERVER_PINS.json); deps come from the registry at build time
COPY wonderwhy-er-desktop-commander-0.1.39.tgz /opt/dc.tgz
RUN npm install -g --no-audit --no-fund /opt/dc.tgz && rm /opt/dc.tgz \
 && apt-get update -qq && apt-get install -y -qq --no-install-recommends python3 ripgrep procps >/dev/null && rm -rf /var/lib/apt/lists/* \
 && userdel -r node && useradd -m -u 1000 -s /bin/bash -G adm user \
 && mkdir -p /home/user/documents /home/user/Documents /home/user/Archives /home/user/Pictures /home/user/.claude-server-commander /opt/fixture /opt/cs \
 && printf 'print("hello from script.py")\n' > /home/user/script.py \
 && printf 'Quarterly report draft.\n' > /home/user/Documents/report.txt \
 && printf '%%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%%%EOF\n' > /home/user/documents/report.pdf \
 && printf 'JFIF' > /home/user/Pictures/holiday.jpg && printf 'JFIF' > /home/user/Pictures/family.jpg && printf 'PNG' > /home/user/Pictures/logo.png \
 && printf 'Oct 10 09:00:01 host systemd[1]: Started daily cleanup.\nOct 10 09:05:14 host app[2201]: error: connection refused to db:5432\nOct 10 09:06:00 host app[2201]: retry ok\n' > /var/log/syslog \
 && printf '2026-10-10 09:05:14 ERROR connection refused\n2026-10-10 09:07:30 INFO recovered\n' > /var/log/app.log \
 && printf '[2026-10-10 09:05:14] error: upstream timeout\n' > /var/log/error.log \
 && chmod 644 /var/log/syslog /var/log/app.log /var/log/error.log \
 && printf '127.0.0.1 localhost\n127.0.1.1 host\n10.0.0.5 db\n' > /etc/hosts.fixture
COPY config.json /home/user/.claude-server-commander/config.json
COPY entrypoint.sh /opt/cs/entrypoint.sh
COPY snap.sh /opt/cs/snap.sh
RUN chmod 755 /opt/cs/entrypoint.sh /opt/cs/snap.sh && chown -R user:user /home/user
ENTRYPOINT ["/opt/cs/entrypoint.sh"]
