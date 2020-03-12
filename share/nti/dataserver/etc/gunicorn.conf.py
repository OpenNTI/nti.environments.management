import multiprocessing
import os

# Let true and false be synonyms for ease of the templaters
true = True
false = False

proxy_protocol = True
# Listen on all addresses to this port, and locally on this file
bind = [":8081", "unix:/home/ntiuser/buildout/var/run/dataserver.sock"]
# Calculate worker number automatically if not
# specified
workers = "1" or multiprocessing.cpu_count() * 2 + 1
worker_class =  "nti.appserver.nti_gunicorn.GeventApplicationWorker"
logger_class = "nti.appserver.nti_gunicorn.GunicornLogger"
accesslog = "/dev/stderr"
timeout = 1800
preload_app = false
reuse_port = true

forwarded_allow_ips = "" or "*"

# The maximum number of requests a worker will process before
# restarting. Any value greater than zero will limit the number of
# requests a work will process before automatically restarting. This
# is a simple method to help limit the damage of memory leaks. If this
# is set to zero (the default) then the automatic worker restarts are
# disabled.
max_requests = 0

# The maximum number of simultaneous clients. This setting only
# affects the Eventlet and Gevent worker types.
worker_connections = 250

# We want to dump the stack of any greenlet running for more than 5s
# (cpu bound).
raw_env = ['gevent_blocking_trace=False',
'gevent_max_blocking_time=5']

# StatsD connection
statsd_host = "127.0.0.1:9125"
statsd_prefix = 'pserve'
