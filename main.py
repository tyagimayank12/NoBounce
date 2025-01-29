import time
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



TEMP_DIR = tempfile.mkdtemp()


@app.post("/validate-emails")
async def validate_emails(file: UploadFile = File(...)):
    try:
        contents = await file.read()

        # Read input file
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

        # Generate validation ID
        validation_id = str(uuid.uuid4())

        # Save files with validation ID
        refined_path = os.path.join(TEMP_DIR, f"{validation_id}_refined.csv")
        discarded_path = os.path.join(TEMP_DIR, f"{validation_id}_discarded.csv")

        valid_emails.to_csv(refined_path, index=False)
        invalid_emails.to_csv(discarded_path, index=False)

        return {
            "validation_id": validation_id,
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
        if file_type not in ['refined', 'discarded']:
            raise HTTPException(status_code=400, detail="Invalid file type")

        file_path = os.path.join(TEMP_DIR, f"{validation_id}_{file_type}.csv")

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(
            path=file_path,
            filename=f"{'Refined' if file_type == 'refined' else 'Discarded'} - results.csv",
            media_type='text/csv'
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Clean up old files periodically
@app.on_event("startup")
async def startup_event():
    def cleanup_old_files():
        while True:
            time.sleep(3600)  # Check every hour
            current_time = time.time()
            for filename in os.listdir(TEMP_DIR):
                file_path = os.path.join(TEMP_DIR, filename)
                if current_time - os.path.getmtime(file_path) > 86400:  # 24 hours
                    try:
                        os.remove(file_path)
                    except:
                        pass

    import threading
    cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
    cleanup_thread.start()
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