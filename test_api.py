import requests
import os
import pandas as pd
from io import StringIO  # Add this import


def test_api():
    # API endpoint
    url = "https://nobounce-production.up.railway.app/validate-emails"

    file_path = "/Users/mayanktyagi/PycharmProjects/NoBounce/TestBounce.csv"

    if not os.path.exists(file_path):
        print(f"❌ Error: File not found: {file_path}")
        return

    try:
        files = {
            'file': ('TestBounce.csv', open(file_path, 'rb'), 'text/csv')
        }

        print("Sending request...")
        response = requests.post(url, files=files)

        if response.status_code == 200:
            # Read the response into a DataFrame
            df = pd.read_csv(StringIO(response.content.decode('utf-8')))

            # Filter to keep only Valid emails
            valid_emails = df[df['Status'].isin(['Valid', 'Free Email Provider', 'Custom Domain Email'])]

            # Save filtered results
            output_file = 'clean_email_list.csv'
            valid_emails.to_csv(output_file, index=False)

            # Print statistics
            print("\n=== Email Validation Results ===")
            print(f"Total emails processed: {len(df)}")
            print(f"Valid emails: {len(valid_emails)}")
            print(f"Removed emails: {len(df) - len(valid_emails)}")
            print("\nBreakdown of invalid emails:")
            invalid_counts = df[~df['Status'].isin(['Valid', 'Free Email Provider', 'Custom Domain Email'])][
                'Status'].value_counts()
            for status, count in invalid_counts.items():
                print(f"{status}: {count}")

            print(f"\n✅ Clean email list saved to {output_file}")
            print(f"File location: {os.path.abspath(output_file)}")

            # Save invalid emails to a separate file
            invalid_emails = df[~df['Status'].isin(['Valid', 'Free Email Provider', 'Custom Domain Email'])]
            invalid_emails.to_csv('invalid_emails.csv', index=False)
            print(f"Invalid emails saved to: invalid_emails.csv")

        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"❌ Error occurred: {str(e)}")


if __name__ == "__main__":
    test_api()