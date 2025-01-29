from collections import Counter

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
from typing import Dict, Any
import pandas as pd
from io import BytesIO
import sqlite3
import os
import tempfile
import uuid
from datetime import datetime, timedelta

from starlette.responses import FileResponse

from email_validator import EmailValidator
import logging
from ip_pool import IPPool
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="NoBounce Email Validator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Configure storage
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), 'nobounce_uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Initialize validator
validator = EmailValidator([
    '13.61.64.236',
    '13.60.65.138',
    '13.61.100.159',
    '13.53.128.166'
])


# Database initialization
def init_db():
    try:
        db_path = os.path.join(UPLOAD_DIR, 'email_validation.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS validation_files
            (id TEXT PRIMARY KEY,
             original_filename TEXT,
             refined_path TEXT,
             discarded_path TEXT,
             created_at TIMESTAMP,
             stats TEXT)
        ''')
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
        raise


def cleanup_old_files():
    try:
        db_path = os.path.join(UPLOAD_DIR, 'email_validation.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Get files older than 3 days
        three_days_ago = datetime.now() - timedelta(days=3)
        c.execute("SELECT refined_path, discarded_path FROM validation_files WHERE created_at < ?",
                  (three_days_ago,))
        old_files = c.fetchall()

        # Delete files and records
        for refined_path, discarded_path in old_files:
            try:
                if os.path.exists(refined_path):
                    os.remove(refined_path)
                if os.path.exists(discarded_path):
                    os.remove(discarded_path)
            except Exception as e:
                logger.error(f"Error deleting file: {e}")

        c.execute("DELETE FROM validation_files WHERE created_at < ?", (three_days_ago,))
        conn.commit()
        conn.close()
        logger.info("Cleanup completed successfully")
    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")


@app.post("/validate-emails")
async def validate_emails(file: UploadFile = File(...)):
    try:
        contents = await file.read()

        # Read the input file
        if file.filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(contents))
        else:
            df = pd.read_excel(BytesIO(contents))

        if 'Email' not in df.columns:
            raise HTTPException(status_code=400, detail="File must contain an 'Email' column")

        # Process emails
        results = []
        for email in df['Email'].values:
            result = validator.validate_email(email)
            results.append(result)

        # Create results DataFrame
        results_df = pd.DataFrame({
            'Email': df['Email'],
            'Status': [r['details'][0] if r['details'] else 'Valid' for r in results]
        })

        # Split into valid and invalid
        valid_emails = results_df[results_df['Status'] == 'Valid']
        invalid_emails = results_df[results_df['Status'] != 'Valid']

        # Generate filenames
        original_name = os.path.splitext(file.filename)[0]
        refined_filename = f"Refined - {original_name}.csv"
        discarded_filename = f"Discarded - {original_name}.csv"

        # Save files
        valid_emails.to_csv(refined_filename, index=False)
        invalid_emails.to_csv(discarded_filename, index=False)

        return {
            "validation_id": str(uuid.uuid4()),
            "message": "Email validation completed",
            "stats": {
                "total_emails": len(df),
                "valid_emails": len(valid_emails),
                "invalid_emails": len(invalid_emails)
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{validation_id}/{file_type}")
async def download_file(validation_id: str, file_type: str):
    try:
        # Get original filename from the request
        original_name = "TestBounce"  # You might want to store this with validation_id

        if file_type == "refined":
            filename = f"Refined - {original_name}.csv"
        elif file_type == "discarded":
            filename = f"Discarded - {original_name}.csv"
        else:
            raise HTTPException(status_code=400, detail="Invalid file type")

        if not os.path.exists(filename):
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(
            filename,
            media_type='text/csv',
            filename=filename
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    """Initialize database and start cleanup task"""
    init_db()
    cleanup_old_files()  # Initial cleanup

@app.get("/")
async def health_check():
    return {
        "status": "online",
        "message": "NoBounce Email Validator API is running",
        "timestamp": datetime.now().isoformat(),
        "service": "NoBounce Email Validator"
    }


@app.get("/validation-stats")
async def get_stats():
    return {
        "total_checked": len(validator.cache),
        "valid_ratio": sum(1 for v in validator.cache.values() if v == 'Valid') / len(validator.cache) if validator.cache else 0,
        "failure_types": Counter(validator.cache.values())
    }


@app.get("/status")
async def get_status():
    """Get IP pool status"""
    try:
        status = validator.ip_pool.get_status()
        return {
            "status": "online",
            "ip_pool": status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)