# Use the official Python 3.11 slim image
FROM python:3.11-slim

# Install MLflow and required dependencies
RUN pip install --no-cache-dir mlflow psycopg2-binary boto3

# Set the default command to run the MLflow server
# The actual command with all arguments will be supplied by docker-compose.yml
CMD ["mlflow", "server"]
