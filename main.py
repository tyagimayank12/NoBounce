# main.py
from email_validator import EmailValidator
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def main():
    validator = EmailValidator()

    # Test emails
    email_list = [
        'test@yahoo.com',
        'mayanktyagi12@gmail.com',
        'mohit@chawtechsolutions.com',
        'driscy15@aol.com',
        'ctfconnection@tenpincada.com',
        'barbara.graham@urban-gro.com'# Your email
    ]

    for email in email_list:
        try:
            result = validator.validate_email(email)
            logging.info(f"Email: {email}, Status: {result}")
            time.sleep(1)  # Increased delay between checks
        except Exception as e:
            logging.error(f"Error validating {email}: {str(e)}")

if __name__ == "__main__":
    main()