import requests
import pandas as pd
from io import BytesIO


def test_api():
    print("Starting Email Validation Test...")
    url = "https://nobounce-production.up.railway.app/validate-emails"
    file_path = "TestBounce.csv"

    try:
        with open(file_path, 'rb') as f:
            files = {'file': ('TestBounce.csv', f, 'text/csv')}
            response = requests.post(url, files=files)

        if response.status_code == 200:
            result = response.json()

            # Save valid emails
            with open('valid_emails.csv', 'w') as f:
                f.write(result['valid_emails']['content'])
            print("✓ Valid emails saved to 'valid_emails.csv'")

            # Save invalid emails
            with open('invalid_emails.csv', 'w') as f:
                f.write(result['invalid_emails']['content'])
            print("✓ Invalid emails saved to 'invalid_emails.csv'")

            # Print statistics
            stats = result['stats']
            print("\nValidation Statistics:")
            print(f"Total Emails: {stats['total']}")
            print(f"Valid Emails: {stats['valid']}")
            print(f"Invalid Emails: {stats['invalid']}")
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    test_api()