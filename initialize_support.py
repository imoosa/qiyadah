"""Prepare customer-support tables on an existing installation."""
from app import app
from support_assistant import initialize_support_storage

if __name__ == '__main__':
    with app.app_context():
        initialize_support_storage()
    print('Customer Support tables and predefined answers are ready. Existing records were preserved.')
