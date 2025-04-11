# Gunicorn configuration file for TabibMeet Backend

import multiprocessing

# Workers
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"

# Socket
bind = "0.0.0.0:8000"

# Logging
loglevel = "info"
accesslog = "-"
errorlog = "-"

# Restart workers after this many requests
max_requests = 1000
max_requests_jitter = 50

# Timeout (in seconds)
timeout = 120
