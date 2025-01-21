from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import Response, HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import pandas as pd
from io import BytesIO, StringIO
from email_validator import EmailValidator
import os

app = FastAPI()

# Set up templates
templates = Jinja2Templates(directory="templates")

# Initialize validator
validator = EmailValidator(ips=['13.61.64.236'])


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/validate-emails")
async def validate_emails(file: UploadFile = File(...)):
    try:
        contents = await file.read()

        # Handle different file types
        if file.filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(contents))
        else:
            df = pd.read_excel(BytesIO(contents))

        if 'Email' not in df.columns:
            raise HTTPException(status_code=400, detail="File must contain an 'Email' column")

        results = []
        for email in df['Email'].values:
            results.append(validator.validate_email(email))

        # Create results DataFrame
        results_df = pd.DataFrame({
            'Email': df['Email'],
            'Status': results
        })

        # Filter valid emails
        valid_emails = results_df[results_df['Status'].isin(['Valid', 'Free Email Provider', 'Custom Domain Email'])]

        # Create output file
        output = BytesIO()
        if file.filename.endswith('.csv'):
            output_str = valid_emails.to_csv(index=False)
            output = BytesIO(output_str.encode())
            media_type = 'text/csv'
            filename = 'valid_emails.csv'
        else:
            valid_emails.to_excel(output, index=False)
            media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            filename = 'valid_emails.xlsx'

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