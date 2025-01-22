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
from email_validator import EmailValidator
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="NoBounce Email Validator API")

# Configure storage
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), 'nobounce_uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Initialize validator
validator = EmailValidator(ips=['13.61.64.236'])


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
async def validate_emails(file: UploadFile = File(...)) -> Dict[str, Any]:
    try:
        logger.info(f"Processing file: {file.filename}")
        validation_id = str(uuid.uuid4())

        # Read file content
        contents = await file.read()

        # Determine file type and read accordingly
        try:
            if file.filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(BytesIO(contents))
            else:
                df = pd.read_csv(BytesIO(contents))
        except Exception as e:
            logger.error(f"File reading error: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid file format or corrupted file")

        if 'Email' not in df.columns:
            raise HTTPException(status_code=400, detail="File must contain an 'Email' column")

        # Process emails
        results = []
        for email in df['Email'].values:
            try:
                results.append(validator.validate_email(email))
            except Exception as e:
                logger.error(f"Validation error for {email}: {str(e)}")
                results.append("Error: Invalid Email")

        results_df = pd.DataFrame({
            'Email': df['Email'],
            'Status': results
        })

        # Split into valid and invalid emails
        valid_emails = results_df[
            results_df['Status'].isin(['Valid', 'Free Email Provider', 'Custom Domain Email'])
        ]
        invalid_emails = results_df[
            ~results_df['Status'].isin(['Valid', 'Free Email Provider', 'Custom Domain Email'])
        ]

        # Generate filenames
        original_name = os.path.splitext(file.filename)[0]
        refined_filename = f"Refined - {original_name}.csv"
        discarded_filename = f"Discarded - {original_name}.csv"

        # Save files
        refined_path = os.path.join(UPLOAD_DIR, f"{validation_id}_{refined_filename}")
        discarded_path = os.path.join(UPLOAD_DIR, f"{validation_id}_{discarded_filename}")

        valid_emails.to_csv(refined_path, index=False)
        invalid_emails.to_csv(discarded_path, index=False)

        # Store in database
        stats = {
            "total_emails": len(df),
            "valid_emails": len(valid_emails),
            "invalid_emails": len(invalid_emails)
        }

        db_path = os.path.join(UPLOAD_DIR, 'email_validation.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute(
            """INSERT INTO validation_files 
               (id, original_filename, refined_path, discarded_path, created_at, stats) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (validation_id, file.filename, refined_path, discarded_path,
             datetime.now(), str(stats))
        )
        conn.commit()
        conn.close()

        logger.info(f"Processing completed for {file.filename}")
        return {
            "validation_id": validation_id,
            "message": "Email validation completed successfully",
            "stats": stats
        }

    except Exception as e:
        logger.error(f"Processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{validation_id}/{file_type}")
async def download_file(validation_id: str, file_type: str):
    try:
        db_path = os.path.join(UPLOAD_DIR, 'email_validation.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""SELECT refined_path, discarded_path, original_filename 
                    FROM validation_files WHERE id = ?""", (validation_id,))
        result = c.fetchone()
        conn.close()

        if not result:
            raise HTTPException(status_code=404, detail="Validation ID not found")

        refined_path, discarded_path, original_name = result

        if file_type == "refined":
            file_path = refined_path
            filename = f"Refined - {original_name}"
        elif file_type == "discarded":
            file_path = discarded_path
            filename = f"Discarded - {original_name}"
        else:
            raise HTTPException(status_code=400, detail="Invalid file type")

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        with open(file_path, "rb") as file:
            content = file.read()

        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"Download error: {str(e)}")
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


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)