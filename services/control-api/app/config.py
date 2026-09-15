import os


class Settings:
    db_url = os.getenv("SENTINEL_DB_URL", "sqlite:///./sentinel.db")
    api_key = os.getenv("SENTINEL_API_KEY", "change-me-now")
    log_level = os.getenv("SENTINEL_LOG_LEVEL", "INFO")
    scan_max_hosts = int(os.getenv("SENTINEL_SCAN_MAX_HOSTS", "4096"))
    scan_tcp_ports = tuple(int(x) for x in os.getenv(
        "SENTINEL_SCAN_TCP_PORTS",
        "22,53,80,443,445,3389,8006,8080,8443,9100,9123"
    ).split(",") if x.strip())
    agent_online_seconds = int(os.getenv("SENTINEL_AGENT_ONLINE_SECONDS", "120"))
    artifact_dir = os.getenv("SENTINEL_ARTIFACT_DIR", "/opt/sentinel/artifacts")
    prometheus_url = os.getenv("SENTINEL_PROMETHEUS_URL", "http://prometheus:9090")
    admin_user = os.getenv("SENTINEL_ADMIN_USER", "admin")
    admin_password = os.getenv("SENTINEL_ADMIN_PASSWORD", "admin")
    session_secret = os.getenv("SENTINEL_SESSION_SECRET", os.getenv("SENTINEL_API_KEY", "change-me-now"))
    session_hours = int(os.getenv("SENTINEL_SESSION_HOURS", "12"))


settings = Settings()
