# Use official Python base image
FROM python:3.11-slim

# Set environment defaults (can be overridden)
ENV IS_4K_REQUEST=true
ENV AUTO_APPROVE=true

# Install dependencies
RUN pip install requests beautifulsoup4

# Create log directory
RUN mkdir -p /logs

# Copy script
COPY scrape_imdb_and_request.py /app/scrape_imdb_and_request.py

# Set working dir
WORKDIR /app

# Run script
CMD ["python", "scrape_imdb_and_request.py"]

