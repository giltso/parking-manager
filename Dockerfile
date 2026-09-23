# How to package the app so it runs the same anywhere.
#
# A container is the app plus the exact Python and libraries it needs, in one
# bundle. Whatever is missing here is missing at run time, which is the point:
# it proves the app doesn't secretly depend on this laptop.
#
# Build and run it:
#     docker build -t parking-manager .
#     docker run --rm -p 8000:8000 -v parking-data:/data parking-manager

# Pinned to the exact Python this project is written for. "slim" is the small
# variant: no compilers or extras, so there is less to download and less that
# can contain a security problem.
FROM python:3.14-slim

# Two settings that make Python behave well inside a container:
#   PYTHONDONTWRITEBYTECODE  don't leave compiled caches in the image
#   PYTHONUNBUFFERED         print logs immediately instead of holding them
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies are copied and installed before the app's own code. Docker
# caches each step, and this order means editing a Python file doesn't reinstall
# every library, which turns a two-minute rebuild into a two-second one.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now the application itself.
COPY app ./app

# The database lives on a volume, a folder that survives the container being
# replaced. Without this, every update would start from an empty database.
ENV DATABASE_PATH=/data/parking.db
VOLUME ["/data"]

# Run as a user with no special powers. If the app is ever tricked into running
# something, it should not be running it as the machine's administrator.
RUN useradd --create-home --uid 10001 parking \
    && mkdir -p /data \
    && chown -R parking:parking /data /app
USER parking

EXPOSE 8000

# One worker on purpose: the background timer that expires bookings lives inside
# the app, and two workers would mean two timers racing each other (PLAN 7.4).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
