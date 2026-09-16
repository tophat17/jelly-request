FROM python:3.11-slim
WORKDIR /app

# Copy requirements and install Python dependencies. IMDb data comes from its
# JSON API, so no browser or scraping stack is needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create logs directory
RUN mkdir /logs

# Copy application files
COPY *.py .

# Set build-time git information as environment variables
ARG GIT_REVISION=unknown
ARG GIT_BRANCH=unknown
ENV GIT_REVISION=${GIT_REVISION}
ENV GIT_BRANCH=${GIT_BRANCH}

CMD ["python", "main.py"]
