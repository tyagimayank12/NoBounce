# main.py
import os
from typing import Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import pandas as pd
from io import BytesIO
from email_validator import EmailValidator
import uvicorn

app = FastAPI(title="NoBounce - Email Validator")

# Initialize validator with your AWS IP
validator = EmailValidator(ips=['13.61.64.236'])


@app.get("/")
async def read_root() -> Dict[str, str]:
    return {"message": "NoBounce Email Validator API is running"}


@app.post("/validate-emails")
async def validate_emails(file: UploadFile = File(...)) -> StreamingResponse:
    if not file.filename.endswith(('.xls', '.xlsx', '.csv')):
        raise HTTPException(status_code=400, detail="Only Excel (.xls, .xlsx) and CSV files are supported")

    try:
        contents = await file.read()

        if file.filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(contents))
        else:
            df = pd.read_excel(BytesIO(contents))

        if 'Email' not in df.columns:
            raise HTTPException(status_code=400, detail="File must contain an 'Email' column")

        results = []
        for email in df['Email'].values:
            result = validator.validate_email(email)
            results.append(result)

        results_df = pd.DataFrame({
            'Email': df['Email'],
            'Status': results
        })

        output = BytesIO()
        if file.filename.endswith('.csv'):
            output_str = results_df.to_csv(index=False)
            output = BytesIO(output_str.encode())
            media_type = 'text/csv'
            filename = 'validation_results.csv'
        else:
            results_df.to_excel(output, index=False)
            media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            filename = 'validation_results.xlsx'

        output.seek(0)

        return StreamingResponse(
            output,
            media_type=media_type,
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))