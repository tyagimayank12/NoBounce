from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
import sqlite3
import os
from email_validator import EmailValidator
import uuid
import shutil

app = FastAPI(title="NoBounce Email Validator API")

# Initialize validator
validator = EmailValidator(ips=['13.61.64.236'])


# Database initialization
def init_db():
    conn = sqlite3.connect('email_validation.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS validation_files
        (id TEXT PRIMARY KEY,
         original_filename TEXT,
         refined_path TEXT,
         discarded_path TEXT,
         created_at TIMESTAMP)
    ''')
    conn.commit()
    conn.close()


# Create uploads directory if it doesn't exist
os.makedirs('uploads', exist_ok=True)
init_db()


@app.post("/validate-emails")
async def validate_emails(file: UploadFile = File(...)):
    try:
        # Generate unique ID for this validation
        validation_id = str(uuid.uuid4())

        # Read the uploaded file
        contents = await file.read()
        df = pd.read_excel(BytesIO(contents)) if file.filename.endswith(('.xlsx', '.xls')) else pd.read_csv(
            BytesIO(contents))

        if 'Email' not in df.columns:
            raise HTTPException(status_code=400, detail="File must contain an 'Email' column")

        # Process emails
        results = []
        for email in df['Email'].values:
            results.append(validator.validate_email(email))

        results_df = pd.DataFrame({
            'Email': df['Email'],
            'Status': results
        })

        # Split into valid and invalid emails
        valid_emails = results_df[results_df['Status'].isin(['Valid', 'Free Email Provider', 'Custom Domain Email'])]
        invalid_emails = results_df[~results_df['Status'].isin(['Valid', 'Free Email Provider', 'Custom Domain Email'])]

        # Generate output filenames
        original_name = os.path.splitext(file.filename)[0]
        refined_filename = f"Refined - {original_name}.csv"
        discarded_filename = f"Discarded - {original_name}.csv"

        # Save files
        refined_path = f"uploads/{validation_id}_{refined_filename}"
        discarded_path = f"uploads/{validation_id}_{discarded_filename}"

        valid_emails.to_csv(refined_path, index=False)
        invalid_emails.to_csv(discarded_path, index=False)

        # Store in database
        conn = sqlite3.connect('email_validation.db')
        c = conn.cursor()
        c.execute(
            "INSERT INTO validation_files (id, original_filename, refined_path, discarded_path, created_at) VALUES (?, ?, ?, ?, ?)",
            (validation_id, file.filename, refined_path, discarded_path, datetime.now())
        )
        conn.commit()
        conn.close()

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
        conn = sqlite3.connect('email_validation.db')
        c = conn.cursor()
        c.execute("SELECT refined_path, discarded_path, original_filename FROM validation_files WHERE id = ?",
                  (validation_id,))
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
        raise HTTPException(status_code=500, detail=str(e))


# Cleanup task to run daily (you'll need to set up a cron job or scheduler)
def cleanup_old_files():
    conn = sqlite3.connect('email_validation.db')
    c = conn.cursor()

    # Get files older than 3 days
    three_days_ago = datetime.now() - timedelta(days=3)
    c.execute("SELECT refined_path, discarded_path FROM validation_files WHERE created_at < ?", (three_days_ago,))
    old_files = c.fetchall()

    # Delete files and records
    for refined_path, discarded_path in old_files:
        try:
            if os.path.exists(refined_path):
                os.remove(refined_path)
            if os.path.exists(discarded_path):
                os.remove(discarded_path)
        except Exception as e:
            print(f"Error deleting file: {e}")

    c.execute("DELETE FROM validation_files WHERE created_at < ?", (three_days_ago,))
    conn.commit()
    conn.close()


@app.on_event("startup")
async def startup_event():
    init_db()