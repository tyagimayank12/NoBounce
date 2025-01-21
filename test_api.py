import requests
import time
import sys


def test_email_validation(is_local=True):
    # Use local URL for testing
    base_url = "http://0.0.0.0:8000" if is_local else "https://nobounce-production.up.railway.app"
    url = f"{base_url}/validate-emails"

    # Your test file
    file_path = "TestBounce.csv"  # Make sure this file exists

    try:
        # Check if file exists
        with open(file_path, 'rb') as test_file:
            # Send file for validation
            print(f"Sending file to {url}...")
            files = {
                'file': (file_path, test_file, 'text/csv')
            }

            # Add timeout and retry logic
            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                try:
                    response = requests.post(url, files=files)

                    if response.status_code == 200:
                        result = response.json()
                        validation_id = result['validation_id']
                        print("\nValidation Results:")
                        print(f"Validation ID: {validation_id}")
                        print(f"Stats: {result['stats']}")

                        # Download both refined and discarded lists
                        for file_type in ['refined', 'discarded']:
                            download_url = f"{base_url}/download/{validation_id}/{file_type}"
                            download = requests.get(download_url)

                            if download.status_code == 200:
                                filename = f"test_{file_type}.csv"
                                with open(filename, 'wb') as f:
                                    f.write(download.content)
                                print(f"\nDownloaded {file_type} list to {filename}")
                            else:
                                print(f"\nError downloading {file_type} list: {download.status_code}")
                        break
                    else:
                        print(f"Error: {response.status_code}")
                        print(response.text)
                        break
                except requests.exceptions.ConnectionError:
                    retry_count += 1
                    if retry_count == max_retries:
                        print("Error: Could not connect to server. Make sure the server is running.")
                        print("Run 'uvicorn main:app --reload --host 0.0.0.0 --port 8000' first.")
                        sys.exit(1)
                    print(f"Connection failed. Retrying ({retry_count}/{max_retries})...")
                    time.sleep(2)  # Wait 2 seconds before retrying
    except FileNotFoundError:
        print(f"Error: Test file '{file_path}' not found. Please make sure the file exists.")
    except Exception as e:
        print(f"Error occurred: {str(e)}")


if __name__ == "__main__":
    print("Testing locally...")
    test_email_validation(is_local=True)