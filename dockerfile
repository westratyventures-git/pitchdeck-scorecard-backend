FROM python:3.10

# Create app directory
WORKDIR /code

# Install system dependencies for PyMuPDF
RUN apt-get update && apt-get install -y \
    libglib2.0-0 libsm6 libxrender1 libxext6 poppler-utils

# Copy requirements if you have one (optional)
# If you don’t have requirements.txt, we install manually below
# COPY requirements.txt .
# RUN pip install -r requirements.txt

# Install Python dependencies
RUN pip install fastapi uvicorn openai firebase-admin pymupdf gradio

# Copy project
COPY . .

# Expose port
EXPOSE 7860

# Start FastAPI server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
