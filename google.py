import os
import pickle

import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from google.auth.transport.requests import Request

# Define the scopes
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

# Path to the credentials file
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pickle'
if 'code' not in st.session_state:
    st.session_state.code = None


def save_token_to_file(creds):
    with open(TOKEN_FILE, 'wb') as token_file:
        pickle.dump(creds, token_file)


def load_token_from_file():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token_file:
            return pickle.load(token_file)
    return None


def create_flow():
    return Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri='http://localhost:8501/',
    )


def get_drive_service(credentials):
    return build('drive', 'v3', credentials=credentials)


def list_drive_files(service):
    results = (
        service.files()
        .list(
            pageSize=10,
            fields='nextPageToken, files(id, name)',
        )
        .execute()
    )
    items = results.get('files', [])
    return items


def main():
    st.title('Google Drive File Viewer')

    # Create session state variables if they don't exist
    if 'flow' not in st.session_state:
        st.session_state.flow = None

    # Check for authorization code in URL query parameters
    if st.session_state.code is None:
        query_params = st.query_params
        st.session_state.code = query_params.get('code', [None])[0]

    creds = load_token_from_file()

    # If we have a code in the URL, process it
    if st.session_state.code is not None:
        try:
            if st.session_state.flow is None:
                st.session_state.flow = create_flow()

            st.session_state.flow.fetch_token(code=st.session_state.code)
            creds = st.session_state.flow.credentials
            save_token_to_file(creds)

            # Clear the URL parameters
            st.experimental_set_query_params()
            st.success('Successfully authenticated with Google Drive!')
            st.experimental_rerun()
        except Exception as e:
            st.error(f'Authentication failed: {e!s}')

    # If token doesn't exist or is invalid, start the authorization flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                save_token_to_file(creds)
            except Exception:
                creds = None

        if not creds:
            st.session_state.flow = create_flow()
            auth_url, _ = st.session_state.flow.authorization_url(prompt='consent')

            st.markdown("""
            ### Google Drive Authorization Required

            Click the button below to connect to your Google Drive account. You'll be redirected to Google's 
            login page and then back to this app automatically.
            """)

            st.markdown(
                f'[![Login with Google](https://img.shields.io/badge/Login_with-Google-4285F4?style=for-the-badge&logo=google&logoColor=white)]({auth_url})',
            )

            return  # Exit early as we're waiting for authentication

    # If we have valid credentials, list the files
    if creds and creds.valid:
        service = get_drive_service(creds)

        with st.spinner('Loading files from Google Drive...'):
            files = list_drive_files(service)

        if not files:
            st.info('No files found in your Google Drive.')
        else:
            st.subheader('Your Google Drive Files:')

            # Create a more attractive file list with icons
            for file in files:
                col1, col2 = st.columns([1, 6])
                with col1:
                    st.markdown('📄')
                with col2:
                    st.markdown(f'**{file["name"]}**  \n`{file["id"]}`')

            st.success(f'Successfully loaded {len(files)} files from your Google Drive')


if __name__ == '__main__':
    main()
