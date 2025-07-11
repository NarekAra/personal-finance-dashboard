"""Let user create their 'rules', which maps words in the description column to the users predefined subcategories.

The subcategories are then mapped to the users predefined categories.
Users can either create this mapping in the UI or by passing a configuration file (.yml).
Afterwards, users get an overview of the categorized transactions, which they can download as input for the dashboard.
Users can also overwrite the categorizations manually.
"""

import io

import pandas as pd
import streamlit as st
from ruamel.yaml import YAML
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

from utils import (
    categorize_data,
    df_to_excel,
    display_current_categorization_config_structure,
    display_get_configuration_file,
    display_get_transactions_file,
    paths,
    validate_categorize_mapping_config_format,
    validate_data_after_categorization,
)

st.markdown(
    """
    <div class="main-header">Categorize Transactions</div>
    <div class="sub-header">Take Control of Your Finances</div>
    <p>To categorize your transactions:</p>
    <ul>
        <li>Use the 'Current Structure' tab to map rules to your desired categories and subcategories.
        A rule will search for a given word in the 'DESCRIPTION' column of your transactions.</li>
        <li>For your convenience, save the configuration (.yml file).
        In a future session, simply upload this file in the 'Upload Config' tab.</li>
        <li>Upload the transactions that you want to categorize in the 'Upload Transactions' tab.</li>
        <li>Download or modify your categorized transactions in the 'Categorize Transactions' tab.</li>
    </ul>
    """,
    unsafe_allow_html=True,
)

yaml = YAML()


(current_structure, upload_config, upload_transactions, categorize_transactions) = st.tabs([
    'Current Structure',
    'Upload Config',
    'Upload Transactions',
    'Categorize Transactions',
])

with current_structure:
    display_current_categorization_config_structure()
    col1, col2 = st.columns([5, 1])
    with col1.expander('Get current config (.yml):'):
        # for a cleaner overview & let the user copy-paste this to create their own .yml
        stream = io.StringIO()
        yaml.dump(st.session_state.config_to_categorize, stream)
        yaml_str = stream.getvalue()
        st.code(yaml_str, language='yaml')


with upload_config:
    st.info(
        """This file will contain the rules for categorizing your transactions.
        Every transaction should only have 1 subcategory.
        Every subcategory should have exactly 1 category.""",
        icon='ℹ️',
    )

    # Let user upload their configuration file and pass an example file they can download
    with open(paths['example_categories_mapping_config'], 'r') as file:
        example_categories_mapping_config_data = file.read()

    config_path = display_get_configuration_file(
        title='Upload categorization mapping (.yml)',
        example_file=example_categories_mapping_config_data,
    )
    if st.button('Upload the config'):
        if config_path:
            st.session_state.config_to_categorize = yaml.load(config_path)
            for category, subcategories in st.session_state.config_to_categorize['CATEGORIES'].items():
                for subcategory in subcategories:
                    st.session_state._subcategory_to_category[subcategory] = category
            st.rerun()
        else:
            st.error('Please upload a configuration file.')


with upload_transactions:
    st.info(
        """In order to categorize your transactions, only a description is sufficient.
        However, if you would like to use the dashboard later on, it is recommend to have
        an excel file structured like this:""",
        icon='ℹ️',
    )

    data_structure = pd.read_excel(paths['data_structure'])
    st.dataframe(data_structure)
    # Let user upload transactions data
    example_transactions_data = df_to_excel(pd.read_excel(paths['example_transactions']))
    file_path = display_get_transactions_file(
        title='Upload transactions (.xlsx)',
        example_file=example_transactions_data,
    )
    if st.button('Upload the file.'):
        if file_path:
            st.session_state.data_to_categorize = pd.read_excel(file_path)
        else:
            st.error('Please upload a transactions file.')
    if st.session_state.data_to_categorize is not None:
        # Add number input for starting row
        st.session_state.start_row = st.number_input(
            'Start categorizing from row (1-based index, leave at 1 to process all rows):',
            min_value=1,
            max_value=len(st.session_state.data_to_categorize),
            value=1,
            help='Specify which row to start categorizing from. Row 1 is the first row after the header.',
        )


with categorize_transactions:
    if (st.session_state.config_to_categorize is not None) & (st.session_state.data_to_categorize is not None):
        validate_categorize_mapping_config_format(st.session_state.config_to_categorize)
        st.markdown(
            """
            <ul class="feature-list">
                <li>Categories and subcategories have been assgined to all your transactions. </li>
                <li>You can now overwrite any subcategories that got assigned incorrectly. Press
                    <em>'Fill in Category'</em> to update the category based on the configuration file. </li>
                <li>Some transactions, highlighted in <strong>
                    <span style="color: red; font-styl:bold">red</span></strong>,
                    ave not been assigned to any category. </li>
                <li>Consider expanding the configuration file to include these transactions,
                or manually edit them yourself. </li>
            </ul>""",
            unsafe_allow_html=True,
        )

        if st.session_state.updated_categorized_df is None:
            categorized_data = categorize_data(
                st.session_state.data_to_categorize.iloc[st.session_state.start_row - 1 :],
                st.session_state.config_to_categorize,
            )
            validate_data_after_categorization(categorized_data)
            categorized_data = categorized_data.drop(['SUBCATEGORY_COUNT', 'CATEGORY_COUNT'], axis=1)
        else:
            categorized_data = st.session_state.updated_categorized_df

        grid_builder = GridOptionsBuilder.from_dataframe(categorized_data)
        # Make all elements in df editable
        grid_builder.configure_default_column(editable=True, flex=1)
        # Make the subcategory column a dropdown. Not needed for category, as it should
        # be completely dependant on subcategory.
        grid_builder.configure_column(
            'SUBCATEGORY',
            cellEditor='agSelectCellEditor',
            cellEditorParams={'values': sorted(set(st.session_state.config_to_categorize['SUBCATEGORIES'].keys()))},
        )
        grid_options = grid_builder.build()
        # Highlight in red if category is UNKNOWN
        grid_options['defaultColDef']['cellStyle'] = JsCode(
            r"""
            function(cellClassParams) {
                if (cellClassParams.data.CATEGORY == 'UNKNOWN' || cellClassParams.data.SUBCATEGORY == 'UNKNOWN') {
                    return {'background-color': 'red'}
                }
                return {};
                }
        """,
        )
        categorized_data = AgGrid(
            data=categorized_data,
            gridOptions=grid_options,
            allow_unsafe_jscode=True,
            key=f'grid_{st.session_state.AgGrid_number}',
        )['data']

        if st.button('Fill in category'):
            # key has to be renewed for every update
            st.session_state.AgGrid_number += 1
            # categorize again.
            categorized_data = categorize_data(
                categorized_data,
                st.session_state.config_to_categorize,
                first_time=False,
            )
            st.session_state.updated_categorized_df = categorized_data
            st.dataframe(categorized_data)
            st.rerun()

        # Let user download the categorized data
        categorized_data_excel = df_to_excel(categorized_data)
        # Create a download button
        st.download_button(
            label='Download categorized transactions',
            data=categorized_data_excel,
            file_name='categorized_transactions.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    else:
        st.write('Please Upload a config/ create a current mapping structure and upload your transactions data first.')
