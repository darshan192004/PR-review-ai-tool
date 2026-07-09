FROM ubuntu:24.04 AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    jq \
    python3 \
    python3-pip \
    sudo \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade --break-system-packages setuptools

COPY pyproject.toml /tmp/build/
COPY src/ /tmp/build/src/
RUN pip3 install --no-cache-dir --break-system-packages /tmp/build/ && \
    rm -rf /tmp/build/

ARG RUNNER_VERSION=2.335.1
ARG RUNNER_ARCH=x64

RUN mkdir -p /opt/actions-runner && \
    curl -fsSL "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz" \
    -o /tmp/runner.tar.gz && \
    tar xzf /tmp/runner.tar.gz -C /opt/actions-runner && \
    rm /tmp/runner.tar.gz && \
    /opt/actions-runner/bin/installdependencies.sh && \
    rm -rf /var/lib/apt/lists/*

COPY runner-github/entrypoint.sh /opt/actions-runner/
COPY runner-github/configure.sh /opt/actions-runner/
RUN chmod +x /opt/actions-runner/entrypoint.sh /opt/actions-runner/configure.sh && \
    useradd -m runner -u 1001 && \
    chown -R runner:runner /opt/actions-runner && \
    echo "runner ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/runner

FROM base AS dind

RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY runner-github/dind-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/dind-entrypoint.sh

ENV GITHUB_ACTIONS_RUNNER=true
ENV CI_TRIAGE_WATCHER=true
ENV DOCKER_HOST=unix:///var/run/docker.sock

WORKDIR /opt/actions-runner

ENTRYPOINT ["/usr/local/bin/dind-entrypoint.sh"]
