import os

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

random_1k = os.urandom(1 * 1024)
random_20k = os.urandom(20 * 1024)
random_200k = os.urandom(200 * 1024)


app = Starlette(
    routes=[
        Route("/1k", lambda r: PlainTextResponse(random_1k)),
        Route("/20k", lambda r: PlainTextResponse(random_20k)),
        Route("/200k", lambda r: PlainTextResponse(random_200k)),
    ],
)

# Run:
# gunicorn benchmark.server:app -b 127.0.0.1:8000 -n benchmark -w 8 -k uvicorn.workers.UvicornWorker
