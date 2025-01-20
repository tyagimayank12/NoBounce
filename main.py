from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
import pandas as pd
from io import BytesIO
from email_validator import EmailValidator
import os

app = FastAPI()

# Initialize validator with your AWS IP
validator = EmailValidator(ips=['13.61.64.236'])


@app.get("/")
def read_root():
    return {"message": "NoBounce Email Validator API is running"}


@app.post("/validate-emails")
async def validate_emails(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        df = pd.read_csv(BytesIO(contents)) if file.filename.endswith('.csv') else pd.read_excel(BytesIO(contents))

        results = []
        for email in df['Email'].values:
            results.append(validator.validate_email(email))

        output = BytesIO()
        results_df = pd.DataFrame({'Email': df['Email'], 'Status': results})

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
        return Response(
            content=output.getvalue(),
            media_type=media_type,
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)