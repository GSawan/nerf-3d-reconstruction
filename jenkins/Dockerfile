# ═══════════════════════════════════════════════════════════════════════════════
# Neo3D — Jenkins CI Server Dockerfile
#
# Why local Jenkins (not GitHub Actions)?
#   - COLMAP reconstruction requires a Linux environment with specific GPU/OS deps
#   - GitHub Actions free tier has time and storage limits
#   - Local Jenkins = zero cost, full control, runs on your machine
#
# Architecture:
#   - Base: jenkins/jenkins:lts-jdk17 (Long Term Support = stable)
#   - Docker CLI added inside Jenkins so the pipeline can run docker commands
#   - Docker socket is mounted at runtime (docker-compose.jenkins.yml)
#     This gives Jenkins access to the host's Docker daemon — "DinD lite"
#     It's simpler and more reliable than full Docker-in-Docker (DinD)
# ═══════════════════════════════════════════════════════════════════════════════

FROM jenkins/jenkins:lts-jdk17

# Switch to root temporarily to install Docker CLI
USER root

# Install Docker CLI (not daemon — we use socket mounting)
# Also install curl for health checks in pipeline steps
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Add jenkins user to docker group so it can run docker commands without sudo
RUN groupadd -f docker && usermod -aG docker jenkins

# Install Docker Compose CLI plugin (v2 format: `docker compose` not `docker-compose`)
RUN mkdir -p /usr/local/lib/docker/cli-plugins && \
    curl -SL "https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-x86_64" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose && \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Copy the Jenkinsfile into the container for reference
# (In practice, Jenkins pulls it from Git — this is just a fallback)
COPY jenkins/Jenkinsfile /var/jenkins_home/Jenkinsfile.reference

# Switch back to jenkins user
USER jenkins

# Skip the Jenkins setup wizard — we pre-configure via env vars
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"

# Pre-install essential Jenkins plugins
# These are the minimum needed for our pipeline
RUN jenkins-plugin-cli --plugins \
    "git:latest \
    workflow-aggregator:latest \
    docker-workflow:latest \
    timestamper:latest \
    ansicolor:latest \
    build-timeout:latest"
