import requests
import pandas as pd
from io import BytesIO


def test_api():
    print("Starting Email Validation Test...")

    # API endpoint
    url = "https://nobounce-production.up.railway.app/validate-emails"
    file_path = "TestBounce.csv"  # Your test file

    try:
        # Send file for validation
        with open(file_path, 'rb') as f:
            files = {'file': ('TestBounce.csv', f, 'text/csv')}
            print("Sending file for validation...")
            response = requests.post(url, files=files)

        if response.status_code == 200:
            print("\nValidation completed successfully!")
            result = response.json()
            validation_id = result.get('validation_id')

            # Download refined list
            refined_url = f"https://nobounce-production.up.railway.app/download/{validation_id}/refined"
            print("\nDownloading refined (valid) emails...")
            refined_response = requests.get(refined_url)
            if refined_response.status_code == 200:
                with open('valid_emails.csv', 'wb') as f:
                    f.write(refined_response.content)
                print("✓ Valid emails saved to 'valid_emails.csv'")

            # Download discarded list
            discarded_url = f"https://nobounce-production.up.railway.app/download/{validation_id}/discarded"
            print("\nDownloading discarded (invalid) emails...")
            discarded_response = requests.get(discarded_url)
            if discarded_response.status_code == 200:
                with open('invalid_emails.csv', 'wb') as f:
                    f.write(discarded_response.content)
                print("✓ Invalid emails saved to 'invalid_emails.csv'")

            # Show statistics
            try:
                valid_df = pd.read_csv('valid_emails.csv')
                invalid_df = pd.read_csv('invalid_emails.csv')
                print("\nValidation Statistics:")
                print(f"Total Emails Processed: {len(valid_df) + len(invalid_df)}")
                print(f"Valid Emails: {len(valid_df)}")
                print(f"Invalid Emails: {len(invalid_df)}")
            except Exception as e:
                print(f"Error reading result files: {str(e)}")

        else:
            print(f"Error: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    test_api()