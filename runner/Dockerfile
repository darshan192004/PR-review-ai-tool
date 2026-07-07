FROM gitea/act_runner:latest

USER root

RUN apk add --no-cache python3 py3-pip

COPY src/ci_triage_agent /opt/ci_triage_agent/

RUN pip install --no-cache-dir /opt/ci_triage_agent/ && \
    rm -rf /opt/ci_triage_agent/

COPY runner/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
