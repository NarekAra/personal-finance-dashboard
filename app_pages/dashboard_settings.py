"""The user can upload their categorized transactions here.

Afterwards, they can change some configurations to personalize their dashboard.
"""

from typing import Any

import gspread
import pandas as pd
import streamlit as st
from gspread_dataframe import get_as_dataframe
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_javascript import st_javascript

from utils import (
    category_col,
    df_to_excel,
    display_get_transactions_file,
    get_checkbox_option,
    get_checkbox_options,
    get_color_picker_options,
    get_number_input_options,
    paths,
    read_config,
    source_col,
    subcategory_col,
    validate_dashboard_config_format,
    validate_transactions_data,
)

# Load credentials
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

creds = ServiceAccountCredentials.from_json_keyfile_dict(
    keyfile_dict={
        'type': st.secrets['google']['type'],
        'project_id': st.secrets['google']['project_id'],
        'private_key_id': st.secrets['google']['private_key_id'],
        'private_key': st.secrets['google']['private_key'],
        'client_email': st.secrets['google']['client_email'],
        'client_id': st.secrets['google']['client_id'],
        'auth_uri': st.secrets['google']['auth_uri'],
        'token_uri': st.secrets['google']['token_uri'],
        'auth_provider_x509_cert_url': st.secrets['google']['auth_provider_x509_cert_url'],
        'client_x509_cert_url': st.secrets['google']['client_x509_cert_url'],
        'universe_domain': st.secrets['google']['universe_domain'],
    },
    scopes=scope,
)

client = gspread.authorize(creds)


def display_header() -> None:
    """Display the header."""
    st.title('Financial Dashboard Configuration')
    st.subheader('Transactions Data')


def _reload() -> None:
    """Reload the page."""
    st_javascript('window.location.reload()')
    _reload()


def handle_file_upload() -> pd.DataFrame | None:
    """Handle the upload of a file for the dashboard.

    This regards the categorized transactions.
    """
    next_step = 'Update' if (st.session_state.get('df_fetched') is not None) else 'Upload'
    col1, _, col2 = st.columns([2, 1, 2])

    with col1:
        example_categorized_transactions = pd.read_excel(paths['example_categorized_transactions'])

        example_categorized_transactions = df_to_excel(example_categorized_transactions)

        file_path = display_get_transactions_file(
            f'{next_step} your transactions (.xlsx).',
            example_categorized_transactions,
        )
        # User input
        st.write(
            f"You can also upload a Google Sheet link which is visible for 'everyone with link'. Do not forget to click {next_step} the file.",
        )
        sheet_url = st.text_input('Paste your Google Sheet link:')

    st.info('The transactions should be structured like this:', icon='ℹ️')
    st.dataframe(pd.read_excel(paths['categorized_data_structure']))
    with col2:
        if st.button(f'{next_step} the file.'):
            df_fetched = None
            if file_path:
                df_fetched = pd.read_excel(file_path)
            if sheet_url:
                try:
                    # Extract the sheet ID
                    sheet_id = sheet_url.split('/d/')[1].split('/')[0]

                    # Open sheet by ID
                    sheet = client.open_by_key(sheet_id).sheet1  # First tab
                    df_fetched = get_as_dataframe(sheet)

                except Exception as e:
                    st.error(f'Error loading sheet: {e}')
            if df_fetched is not None:
                df_fetched['DATE'] = df_fetched['DATE'].astype(str)
                if 'TAG' in df_fetched.columns:  # TODO: dont hardcod
                    df_fetched['TAG'] = df_fetched['TAG']
                df_fetched = df_fetched.fillna('')
                # we should probably not validate twice
                validate_transactions_data(df_fetched)
                st.session_state.cookie_manager.set('file_exists', True, 'file_exists')
                return df_fetched
            st.error('Please upload a file.')

    return None


def display_reset_dashboardconfig_button() -> None:
    """Button to reset the dasboard config to default settings."""
    # Allow the user to reset the value of the config to the default one.
    # Sometimes the configs can also give errors, this will solve these errors.
    # These errors can happen if the user changes the config, but does not
    # update the data.
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button('Reset config'):
            st.session_state.dashboardconfig = read_config(paths['default_dashboard_config'])
            with col2:
                st.success('Config reset.')
    with col2:
        st.markdown(
            """You can reset your config at any time and start over.
            This is also useful if you upload new data that is not compatible with the current config.""",
        )


def handle_income_category_selection(categories: list[str], config: dict[str, Any]) -> str:
    """Selectbox for the income category.

    We first try to suggest as default value the category INCOME if that exists.
    """
    # The user is free to asign any category to be their "income" category
    # The subcategories from these category will be used to construct the pieplot
    # In the default config we already suggest a category "INCOME".
    # If this is not a category of the user, then show them their first category
    # as derived by the income_category_index
    if 'income_category' in config:
        if config['income_category'] not in categories:
            st.session_state.income_category_index = 0
        else:
            st.session_state.income_category_index = categories.index(config['income_category'])
    else:
        st.session_state.income_category_index = 0

    return st.selectbox('Income category', options=categories, index=st.session_state.income_category_index)


def display_config_options() -> dict[str, Any]:
    """Display all the options of the config to customize the dashboard."""
    categories = sorted(st.session_state.df_fetched[category_col].unique())
    sources = [*sorted(st.session_state.df_fetched[source_col].unique()), 'Total']

    st.header('General Settings')
    display_reset_dashboardconfig_button()

    st.session_state.dashboardconfig['display_data'] = st.checkbox('Display transactions', value=True)
    st.session_state.dashboardconfig['currency'] = st.text_input(
        'Currency symbol',
        value=st.session_state.dashboardconfig.get('currency', ''),
        max_chars=3,
    )

    st.header('Chart Settings')
    st.session_state.dashboardconfig['hidden_categories_from_barplot'] = get_checkbox_options(
        categories,
        st.session_state.dashboardconfig,
        'hidden_categories_from_barplot',
    )

    st.subheader('Lineplot Colors')
    st.session_state.dashboardconfig['random_lineplot_colors'] = get_checkbox_option(
        'Random colors',
        st.session_state.dashboardconfig,
        'random_lineplot_colors',
    )
    st.session_state.dashboardconfig['lineplot_colors'] = (
        {}
        if st.session_state.dashboardconfig['random_lineplot_colors']
        else get_color_picker_options(sources, st.session_state.dashboardconfig, 'lineplot_colors')
    )
    st.subheader('Lineplot Width')
    st.session_state.dashboardconfig['lineplot_width'] = get_number_input_options(
        sources,
        value=3,
        min_value=1,
        max_value=10,
        config=st.session_state.dashboardconfig,
        config_name='lineplot_width',
    )

    st.subheader('Category Settings')
    st.session_state.dashboardconfig['income_category'] = handle_income_category_selection(
        categories,
        st.session_state.dashboardconfig,
    )

    st.subheader('Pieplot Colors')
    income_sources = get_income_sources(
        st.session_state.df_fetched,
        st.session_state.dashboardconfig['income_category'],
    )
    st.session_state.dashboardconfig['pieplot_colors'] = get_color_picker_options(
        income_sources,
        st.session_state.dashboardconfig,
        'pieplot_colors',
    )

    st.header('Financial Goals')
    st.session_state.dashboardconfig['goals'] = get_number_input_options(
        categories,
        value=None,
        min_value=0,
        max_value=None,
        config=st.session_state.dashboardconfig,
        config_name='goals',
    )
    st.session_state.dashboardconfig['goals'] = {
        k: v for k, v in st.session_state.dashboardconfig['goals'].items() if v is not None
    }

    return st.session_state.dashboardconfig


def get_income_sources(transactions_df: pd.DataFrame, income_category: str) -> list[str]:
    """Get all the subcategories of transactions with category income."""
    return sorted(transactions_df[transactions_df[category_col] == income_category][subcategory_col].unique())


display_header()

df_fetched = None

uploaded_df = handle_file_upload()
if uploaded_df is not None:
    st.session_state.df_fetched = uploaded_df
if st.session_state.df_fetched is not None:  # todo: what is this?
    validate_transactions_data(st.session_state.df_fetched)
    updated_config = display_config_options()
    validate_dashboard_config_format(updated_config)
