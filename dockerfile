FROM python:3.10

# Create app directory
WORKDIR /code

# Install system dependencies for PyMuPDF
RUN apt-get update && apt-get install -y \
    libglib2.0-0 libsm6 libxrender1 libxext6 poppler-utils && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# (Make sure you have requirements.txt in repo)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Start FastAPI server
# Your file uses: api = FastAPI()
# So import path is main:api   (if file name is main.py)
CMD ["uvicorn", "main:api", "--host", "0.0.0.0", "--port", "8000"]
