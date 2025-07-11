"""Dashboard utils."""

import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

import altair as alt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import streamlit as st
import streamlit_shadcn_ui as ui
from polars.dataframe import DataFrame
from streamlit_extras.mention import mention

from utils import amount_col, category_col_mapping, colors, source_col, time_frame_mapping, type_col


class CalculateUtils:
    """Provides utility functions for calculating various metrics and statistics related to transactions and spending.

    The `CalculateUtils` class contains the following static methods:

    - `calculate_transactions_per_category`: Calculates the total transactions per category over time.
    - `calculate_income_outcome`: Calculates the income and outcome balance for a given source over time.
    - `calculate_net_value`: Calculates the net value for all sources over time.
    - `calculate_goals`: Calculates and compares actual spending against predefined spending goals.
    """

    @staticmethod
    def calculate_transactions_per_category(
        transactions: pl.DataFrame,
        category_col: str,
        time_frame_col: str,
    ) -> pl.DataFrame:
        """Calculates the transactions per category. Aggregated on category and time."""
        transactions = (
            transactions.group_by(time_frame_col, category_col)
            .agg(pl.sum(amount_col).alias(amount_col))
            .sort(category_col, time_frame_col)
            .select(time_frame_col, category_col, amount_col)
        )
        return transactions

    @staticmethod
    def calculate_income_outcome(
        transactions: pl.DataFrame,
        source: List[str],
        time_frame_col: str,
        category_col: str,
    ) -> pl.DataFrame:
        """Calculates the income and outcome balance for a given source over time."""
        distinct_time = transactions.select(time_frame_col).unique()
        distinct_type = transactions.select(type_col).unique()
        distinct_time_type = distinct_type.join(distinct_time, how='cross')
        transactions = transactions.filter(transactions[source_col].is_in(source))
        transactions = transactions.filter(transactions[category_col] != 'TRANSFERS')  # TODO: MAKE THIS A CONSTANT

        income_outcome = (
            distinct_time_type.join(
                transactions.group_by(time_frame_col, type_col).agg(pl.sum(amount_col).alias(amount_col)),
                on=[time_frame_col, type_col],
                how='left',
            )
            .sort(type_col, time_frame_col)
            .with_columns(AMOUNT=pl.col(amount_col).abs())
            .fill_null(0)
            .select(time_frame_col, type_col, amount_col)
        )

        return income_outcome

    @staticmethod
    def calculate_net_value(transactions: pl.DataFrame, time_frame_col: str) -> pl.DataFrame:
        """Calculates the net value for all sources over time."""
        distinct_sources = transactions.select(source_col).unique()
        distinct_time = transactions.select(time_frame_col).unique()

        net_value_per_source = (
            distinct_sources.join(distinct_time, how='cross')
            .join(
                transactions.group_by([source_col, time_frame_col])
                .agg(pl.sum(amount_col).alias('NET_VALUE'))
                .sort(source_col, time_frame_col)
                .with_columns(
                    pl.cum_sum('NET_VALUE')
                    .sort_by(time_frame_col, descending=False)
                    .over(source_col)
                    .alias('NET_VALUE'),
                ),
                on=[source_col, time_frame_col],
                how='left',
            )
            .sort([source_col, time_frame_col])
            .with_columns(pl.exclude(source_col).forward_fill().over(source_col))
            .with_columns((pl.col('NET_VALUE') - pl.col('NET_VALUE').shift(1).over(source_col)).alias('ToT'))
            .fill_null(0)
            .select(time_frame_col, 'NET_VALUE', source_col, 'ToT')
        )

        net_value_total = (
            net_value_per_source.group_by(time_frame_col)
            .agg(pl.sum('NET_VALUE').alias('NET_VALUE'))
            .with_columns(pl.lit('Total').alias(source_col))
            .sort(time_frame_col)
            .fill_null(0)
            .with_columns((pl.col('NET_VALUE') - pl.col('NET_VALUE').shift(1).over(source_col)).alias('ToT'))
            .fill_null(0)
            .select(time_frame_col, 'NET_VALUE', source_col, 'ToT')
        )

        net_value = pl.concat([net_value_total, net_value_per_source])

        return net_value

    @staticmethod
    def calculate_goals(transactions: pl.DataFrame, goal_spending: Dict[str, int]) -> pd.DataFrame:
        """Calculate and compare actual spending against predefined goals."""
        # Normalize goal spending data
        normalized_data = list(goal_spending.items())
        goals_df = pd.DataFrame(normalized_data, columns=['CATEGORY', 'MAX_AMOUNT'])
        # Calculate actual spending per category
        actual_spending = CalculateUtils.calculate_transactions_per_category(
            transactions,
            'CATEGORY',
            'YEAR_MONTH',
        ).to_pandas()

        # Determine the date range
        min_date, max_date = (actual_spending['YEAR_MONTH'].min(), actual_spending['YEAR_MONTH'].max())

        # Create a complete date range DataFrame
        date_range = pd.date_range(start=min_date, end=max_date, freq='MS').strftime('%Y-%m').tolist()
        date_range_df = pd.DataFrame(date_range, columns=['YEAR_MONTH'])

        # Create all possible combinations of YEAR_MONTH and CATEGORY
        all_combinations = pd.MultiIndex.from_product(
            [date_range_df['YEAR_MONTH'], actual_spending['CATEGORY'].unique()],
            names=['YEAR_MONTH', 'CATEGORY'],
        )
        all_combinations_df = pd.DataFrame(index=all_combinations).reset_index()

        # Merge actual spending with all combinations to fill missing months/categories with 0
        actual_spending = all_combinations_df.merge(
            actual_spending,
            on=['CATEGORY', 'YEAR_MONTH'],
            how='left',
        ).fillna(0)

        # Merge actual spending with goal data
        comparison = actual_spending.merge(goals_df, on='CATEGORY', how='inner')

        # Determine if goals were achieved
        comparison['GOAL_ACHIEVED'] = -comparison['MAX_AMOUNT'] < comparison['AMOUNT']

        # Add a human-readable month column
        comparison['MONTH'] = pd.to_datetime(comparison['YEAR_MONTH']).dt.strftime('%B %Y')

        # Create a pivot table to summarize goal achievements per month and category
        pivot_table_goals = (
            pd.pivot_table(
                comparison,
                values='GOAL_ACHIEVED',
                index=['MONTH', 'YEAR_MONTH'],
                columns='CATEGORY',
                aggfunc='sum',
            )
            .sort_values('YEAR_MONTH')
            .reset_index(level='YEAR_MONTH')
            .drop(columns=['YEAR_MONTH'], axis=1)
            .T
        )

        return pivot_table_goals


class PlotUtils:
    """Functions for plotting."""

    def __init__(self, config_file: Dict[str, Any]):
        """Initialize the PlotUtils class."""
        self.config_file = config_file
        if 'lineplot_colors' not in self.config_file:
            self.config_file['lineplot_colors'] = {}
        if 'lineplot_width' not in self.config_file:
            self.config_file['lineplot_width'] = {}
        if 'hidden_categories_from_barplot' not in self.config_file:
            self.config_file['hidden_categories_from_barplot'] = []

    def _plot_net_value_line_plot(self, transactions: DataFrame, time_frame_col: str) -> None:
        """Plot a line plot of net value for all sources over time."""
        # Assuming df, time_frame_col, and SOURCE_COL are defined
        fig = px.line(transactions, x=time_frame_col, y='NET_VALUE', color=source_col)

        # Update traces with custom colors and line widths
        for trace in fig.data:
            source = trace.name  # Get the name of the source
            trace.update(
                line={
                    'color': self.config_file['lineplot_colors'].get(source),
                    'width': self.config_file['lineplot_width'].get(source),
                },
            )

        # Update layout
        fig.update_layout(yaxis_title='Net value')

        # Plot the figure with Streamlit
        st.plotly_chart(fig, use_container_width=True)

    def _plot_transactions_per_category(self, transactions: DataFrame, category_col: str, time_frame_col: str) -> None:
        """Plot a bar plot of transactions per category."""
        fig = px.bar(
            transactions,
            x=time_frame_col,
            y=amount_col,
            color=category_col,
            category_orders={time_frame_col: transactions[time_frame_col].unique().sort().to_list()},
        )
        fig.update_layout(yaxis_title='Amount')
        fig_go = go.Figure(fig)

        [
            trace.update(visible='legendonly')
            for trace in fig_go.data
            if trace.name in self.config_file['hidden_categories_from_barplot']
        ]

        st.plotly_chart(fig_go, use_container_width=True)

    def _plot_lineplot_income_outcome(self, transactions: DataFrame, time_frame_col: str) -> None:
        """Plot a line plot of income and outcome for a given source over time."""
        fig = px.bar(transactions, x=time_frame_col, y=amount_col, color=type_col, barmode='group')
        fig.update_layout(yaxis_title='Amount')
        st.plotly_chart(fig, use_container_width=True)

    def _plot_net_value_tiles(self, transactions: DataFrame, time_frame_col: str, all_sources: List[str]) -> None:
        """Plot tiles of the net value for all sources.

        For the most recent timeframe and a ToT (Time over Time) difference with the previous timeframe.
        """
        last_period = transactions.select(pl.col(time_frame_col).max()).item()
        transactions = transactions.filter(pl.col(time_frame_col) == last_period)
        n_cols = 3
        cols = st.columns(n_cols)
        for i, source in enumerate([*all_sources, 'Total']):
            source_data = transactions.filter(pl.col(source_col) == source)
            net_value_source = source_data.select('NET_VALUE').item()
            ToT_net_value_source = source_data.select('ToT').item()
            with cols[i % n_cols]:
                ui.metric_card(
                    source,
                    f'{net_value_source: .2f}',
                    f'{ToT_net_value_source:.2f}' + self.config_file['currency'],
                )

    def plot_pieplot(self, transactions: DataFrame) -> alt.Chart:
        """Plot a pie chart of the data."""
        transactions = transactions.to_pandas()
        operation_select = alt.selection_single(fields=['SUBCATEGORY'], empty='all')
        if self.config_file['pieplot_colors']:
            scale = alt.Scale(
                domain=list(self.config_file['pieplot_colors'].keys()),
                range=list(self.config_file['pieplot_colors'].values()),
            )
        else:
            scale = alt.Scale(domain=transactions['SUBCATEGORY'].to_list())

        # Create the pie chart
        pie_plot = (
            alt.Chart(transactions)
            .mark_arc(innerRadius=50)
            .encode(
                theta=alt.Theta(field='AMOUNT', type='quantitative', aggregate='sum'),
                color=alt.Color(field='SUBCATEGORY', type='nominal', scale=scale, title='Income sources'),
                opacity=alt.condition(operation_select, alt.value(1), alt.value(0.50)),
            )
            .add_selection(operation_select)
        )
        return pie_plot

    def _plot_goals_heatmap(self, transactions: DataFrame) -> go.Figure:
        """Plot a heatmap of goal achievements."""
        colorscale = [  # "ylgn" colorscale
            [0, 'rgb(255,255,229)'],
            [1, 'rgb(0,69,41)'],
        ]
        hovertext = [
            [
                f'Month: {month}<br>Category: {category}<br>Goal: {"ACHIEVED" if value == 1 else "NOT ACHIEVED"}'
                for month, value in zip(transactions.columns, values)
            ]
            for category, values in transactions.iterrows()
        ]

        heatmap = go.Heatmap(
            z=transactions,
            colorscale=colorscale,
            x=list(transactions.columns),
            y=list(transactions.index),
            hoverinfo='text',
            text=hovertext,
            showscale=False,
        )

        # Get the years
        years = [x for x in list(transactions.columns) if 'January' in x]
        offset = 0.5

        # Create a list of lines, one for each year
        scatter_lines = [
            {
                'type': 'line',
                'x0': i,
                'y0': -offset,
                'x1': i,
                'y1': len(list(transactions.index)) - offset,
                'line': {'color': '#DDDDDD', 'width': 2},
            }
            for i in years
        ]

        scatter_lines = [
            {
                'type': 'line',
                'x0': -offset,
                'y0': i + offset,
                'x1': len(list(transactions.columns)) - offset,
                'y1': i + offset,
                'line': {'color': '#DDDDDD', 'width': 2},
            }
            for i in range(len(list(transactions.index)) - 1)
        ]

        layout = go.Layout(shapes=scatter_lines)
        fig = go.Figure(data=[heatmap], layout=layout)
        return fig

    def display_net_value(self, transactions: pl.DataFrame, time_frame_col: str, all_sources: List[str]) -> None:
        """Display the net value as a line plot over time and as tiles."""
        net_value = CalculateUtils.calculate_net_value(transactions, time_frame_col)
        a, b = st.columns([6, 4])
        with a:
            self._plot_net_value_line_plot(net_value, time_frame_col)
        with b:
            self._plot_net_value_tiles(net_value, time_frame_col, all_sources)

    def display_income_outcome(
        self,
        transactions: pl.DataFrame,
        source: List[str],
        time_frame_col: str,
        category_col: str,
    ) -> None:
        """Display the income and outcome for the selected source over time as a lineplot.

        Args:
            transactions (pl.DataFrame): Input DataFrame containing transaction data.
            source (List[str]): List of source names to filter the data.
            time_frame_col (str): Name of the column containing time frame information.
            category_col (str): Name of the column containing category information.
        """
        income_outcome = CalculateUtils.calculate_income_outcome(transactions, source, time_frame_col, category_col)
        self._plot_lineplot_income_outcome(income_outcome, time_frame_col)

    def display_transactions_per_category(
        self,
        transactions: pl.DataFrame,
        category_col: str,
        time_frame_col: str,
    ) -> None:
        """Display the transactions per category over time as a barplot.

        Args:
            transactions (pl.DataFrame): Input DataFrame containing transaction data.
            category_col (str): Name of the column containing category information.
            time_frame_col (str): Name of the column containing time frame information.
        """
        transactions_per_category = CalculateUtils.calculate_transactions_per_category(
            transactions,
            category_col,
            time_frame_col,
        )
        self._plot_transactions_per_category(transactions_per_category, category_col, time_frame_col)

    def display_pieplot(self, transactions: pl.DataFrame) -> alt.Chart:
        """Display a pie plot of income sources.

        Args:
            transactions (pl.DataFrame): Input DataFrame containing transaction data.

        Returns:
            alt.Chart: Altair chart object representing the pie plot, or None if no data is available.
        """
        data = (
            transactions.filter(pl.col('CATEGORY') == self.config_file['income_category'])
            .group_by('SUBCATEGORY')
            .agg(pl.sum('AMOUNT').alias('AMOUNT'))
            .filter(pl.col('AMOUNT') > 0)
            .sort('SUBCATEGORY')
        )
        pieplot = None
        if data.shape[0] > 0:
            pieplot = self.plot_pieplot(data)
        return pieplot

    def display_goals_heatmap(self, transactions: pl.DataFrame) -> go.Figure:
        """Display a heatmap of goal achievements.

        Args:
            transactions (pl.DataFrame): Input DataFrame containing transaction data.

        Returns:
            go.Figure: Plotly figure object representing the heatmap.
        """
        goals_df = CalculateUtils.calculate_goals(transactions, self.config_file['goals'])
        heatmap = self._plot_goals_heatmap(goals_df)
        return heatmap


def display_faq() -> None:
    """Display frequently asked questions and their answers in expandable sections."""
    with st.expander('**How do I get my transactions?**'):
        st.markdown(
            """
        Some bank offer a download of your transactions in a `CSV` or `Excel` format. For other types of transactions,
        you can manually add them to the file (e.g. cash transactions).
        """,
        )

    with st.expander('**What is the description column in the example transaction file?**'):
        st.markdown(
            """
        This column is not required for the dashboard, however, it is recommend to use this column
        to add all the information about the transaction provided by the bank
        (e.g. description, counterparty account number, name, location etc.).

        It can be used to classify the transactions in categories before providing them to the dashboard.
        """,
        )

    with st.expander('**How do I assign categories to transactions?**'):
        st.markdown(
            """
        This is a difficult task. I suggest using excel or python to automatically classify
        the transactions based on the value in the description column.

        E.g. All transactions with the word "McDonalds" in the description can be
        in the "FOOD" category and "FAST-FOOD" subcategory.

        After that, you can manually go through the transactions,
        correct any mistakes and fill in unclassified transactions.

        If you are not experienced with excel or python, you can use
        [this application](https://personalfinancedashboard.streamlit.app/categorize_transactions).
        """,
            unsafe_allow_html=True,
        )

    with st.expander('**What categories should I have?**'):
        st.markdown(
            """
        I suggest having a few special categories:
        * __TRANSFERS__: This is used to cancel out transfers between your accounts.
        * __UNKNOWN__: This subcategory will be automaticaly assigned to transactions that were not classified.
        Do not specify this category or subcategory yourself.
        * __STARTING_BALANCE__: This is used to set the starting balance of your accounts
        if you want to start tracking from a certain date.

        Additionaly, you should specify a category named __INCOME__ for your income,
        this is required to generate the piepelot. You can change the category name in the configuration file.

        Aside from these categories, you can add as many categories or subcategories as you want.
        """,
        )
        st.stop()


def display_contact_info() -> None:
    """Display contact information and links in the sidebar."""
    with st.sidebar:
        st.markdown(
            """
        Get in touch / notify any bugs:
        """,
        )
        mention(label='Narek Arakelyan', icon='github', url='https://github.com/NarekAra')


def display_data(data: pl.DataFrame) -> None:
    """Display data in a dataframe."""
    if st.session_state.dashboardconfig['display_data']:
        with st.expander('Data Preview'):
            name = st.text_input('Filter the data')
            if name:
                filtered_data = data.filter(
                    pl.any_horizontal(pl.col('*').cast(pl.Utf8).str.to_lowercase().str.contains(name.lower())),
                )
            else:
                filtered_data = data
            st.dataframe(filtered_data)


def display_date_picker(first_and_last_date: Tuple[dt.date, dt.date]) -> Tuple[dt.date, dt.date]:
    """Display a date picker for selecting a date range."""
    return ui.date_picker(key='date_picker', mode='range', label='Selected Range', default_value=first_and_last_date)


def display_get_transactions_file(title: str, example_file: Optional[bytes] = None) -> DataFrame:
    """Display a file uploader for transaction data.

    And an optional example file download button.
    """
    uploaded_file = st.file_uploader(title, key=title)
    if example_file is not None:
        st.download_button(
            label='Download example',
            data=example_file,
            file_name='example_transactions_file.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    return uploaded_file


def display_tabs() -> Tuple[str, str]:
    """Display tabs for selecting e.g. time frame and category."""

    def _create_tabs(mapping):
        # Key is arbitrary here.
        return mapping.get(
            ui.tabs(options=mapping.keys(), default_value=next(iter(mapping.keys())), key=next(iter(mapping.keys()))),
        )

    time_frame_section, category_section, _ = st.columns([3, 3, 6])
    with time_frame_section:
        time_frame_col = _create_tabs(time_frame_mapping)
    with category_section:
        category_col = _create_tabs(category_col_mapping)
    return time_frame_col, category_col


def display_sources(all_sources: List[str]) -> List[str]:
    """Display a multi-select widget for choosing sources."""
    sources = st.multiselect(label='Sources', options=all_sources, default=all_sources)
    return sources


def display_get_configuration_file(title: str, example_file: Optional[str] = None) -> Dict[Any, Any]:
    """Display a file uploader for configuration file.

    And an optional example file download button.
    """
    uploaded_file = st.file_uploader(title, key=title)
    if example_file is not None:
        # Create a download button
        st.download_button(
            label='Download example',
            data=example_file,
            file_name='example_dashboard_config.yaml',
            mime='application/x-yaml',
        )
    return uploaded_file


MAX_COLS = 4


def _get_config_settings(config: Dict[str, Any], config_name: str) -> Any:
    """Get the settings for a given config name."""
    return config.get(config_name) if config is not None else None


def get_checkbox_option(option: str, config: Dict[str, Any], config_name: str) -> bool:
    """Create a single checkbox with a given option."""
    # If there is already a value in the config, fetch that
    config_settings = _get_config_settings(config, config_name)
    return st.checkbox(option, value=config_settings)


def get_checkbox_options(options: List[str], config: Dict, config_name: str) -> List[str]:
    """Create a grid of checkboxes for given options."""
    # If there is already a value in the config, fetch that
    config_settings = _get_config_settings(config, config_name)

    # Define number of columns
    n_cols = min(len(options), MAX_COLS)
    selected_options = []

    for i in range(0, len(options), n_cols):
        cols = st.columns(n_cols)
        for col, option in enumerate(options[i : i + n_cols]):
            with cols[col]:
                # Get old default value of checkboxes, if none exist, set to False
                if st.checkbox(option, value=(option in config_settings) if config_settings else False):
                    selected_options.append(option)

    return selected_options


def get_color_picker_options(options: List[str], config: Dict, config_name: str) -> Dict[str, str]:
    """Create a grid of color pickers for given options."""
    config_settings = _get_config_settings(config, config_name)

    n_cols = min(len(options), MAX_COLS)
    color_options = {}

    for i in range(0, len(options), n_cols):
        cols = st.columns(n_cols)
        for col, option in enumerate(options[i : i + n_cols]):
            with cols[col]:
                color_option = colors[col % len(colors)]
                color = st.color_picker(
                    label=f'Color for {option}',
                    key=option,
                    value=(
                        config_settings[option]
                        if config_settings is not None and option in config_settings
                        else color_option
                    ),
                )
                color_options[option] = color

    return color_options


def get_number_input_options(
    options: List[str],
    value: Optional[float],
    min_value: float,
    max_value: Optional[float],
    config: Dict,
    config_name: str,
) -> Dict[str, float]:
    """Create a grid of number inputs for given options."""
    # Same as get_checkbox_options but for number inputs
    config_settings = _get_config_settings(config, config_name)
    n_cols = min(len(options), MAX_COLS)
    selected_options = {}

    for i in range(0, len(options), n_cols):
        cols = st.columns(n_cols)
        for col_index, option in enumerate(options[i : i + n_cols]):
            with cols[col_index]:
                input_val = st.number_input(
                    option,
                    value=(config_settings.get(option, value) if config_settings else value),
                    min_value=min_value,
                    max_value=max_value,
                )
                selected_options[option] = input_val

    return selected_options


def _add_category(category: str) -> None:
    """Add a category to the config."""
    if category and category not in st.session_state.config_to_categorize['CATEGORIES']:
        st.session_state.config_to_categorize['CATEGORIES'][category] = []
        st.rerun()
    elif category in st.session_state.config_to_categorize['CATEGORIES']:
        st.warning(f"Category '{category}' already exists. Please use a different name.")
        st.stop()
    else:
        st.warning('Please enter a category name.')
        st.stop()


def _add_subcategory(category: str, subcategory: str) -> None:
    """Add a subcategory to the config."""
    if category and subcategory and subcategory not in st.session_state.config_to_categorize['SUBCATEGORIES']:
        st.session_state.config_to_categorize['CATEGORIES'][category].append(subcategory)
        st.session_state.config_to_categorize['SUBCATEGORIES'][subcategory] = []
        st.session_state._subcategory_to_category[subcategory] = category
        st.rerun()
    elif not subcategory:
        st.warning('Please enter a subcategory')
        st.stop()
    else:
        st.warning(f"Subcategory '{subcategory}' already exists. Please use a different name.")
        st.stop()


def _add_rule(rule: str, subcategory: str) -> None:
    """Add a rule to the config."""
    if rule:
        if rule not in st.session_state.config_to_categorize['SUBCATEGORIES'][subcategory]:
            st.session_state.config_to_categorize['SUBCATEGORIES'][subcategory].append(rule)
            st.rerun()
        else:
            st.warning(f"Rule '{rule}' already exists in subcategory '{subcategory}'. Please enter a different rule.")
            st.stop()
    else:
        st.warning('Please enter a rule.')
        st.stop()


def _delete_category(category: str) -> None:
    """Delete a category from the config."""
    st.sidebar.success(st.session_state._subcategory_to_category)
    subcategories = st.session_state.config_to_categorize['CATEGORIES'][category]
    for subcategory in subcategories:
        del st.session_state.config_to_categorize['SUBCATEGORIES'][subcategory]
        del st.session_state._subcategory_to_category[subcategory]
    del st.session_state.config_to_categorize['CATEGORIES'][category]
    st.rerun()


def _delete_subcategory(subcategory: str) -> None:
    """Delete a subcategory from the config."""
    category = st.session_state._subcategory_to_category[subcategory]
    st.sidebar.success(st.session_state._subcategory_to_category)
    st.session_state.config_to_categorize['CATEGORIES'][category].remove(subcategory)
    del st.session_state.config_to_categorize['SUBCATEGORIES'][subcategory]
    del st.session_state._subcategory_to_category[subcategory]
    st.rerun()


def _delete_rule(subcategory: str, rule: str) -> None:
    """Delete a rule from the config."""
    st.session_state.config_to_categorize['SUBCATEGORIES'][subcategory].remove(rule)
    st.rerun()


def _get_rules(subcategory: str) -> List[str]:
    """Get the rules for a subcategory."""
    return st.session_state.config_to_categorize['SUBCATEGORIES'].get(subcategory, [])


def _get_subcategories(category: str) -> List[str]:
    """Get the subcategories for a category."""
    return st.session_state.config_to_categorize['CATEGORIES'][category]


def display_current_categorization_config_structure() -> None:
    """Display the current categorization config structure."""
    # Add new category
    col1, col2 = st.columns([5, 1])
    new_category = col1.text_input(
        'New category name',
        key='new_category_input',
        label_visibility='collapsed',
        placeholder='Enter category name',
    )
    if col2.button('➕ Category', key='add_category_button'):
        _add_category(new_category)
    for category in st.session_state.config_to_categorize['CATEGORIES']:
        col1, col2 = st.columns([5, 1])
        with col1.expander(category):
            if col2.button('🗑️', key=f'del_cat_{category}'):
                _delete_category(category)

            for subcategory in _get_subcategories(category):
                col1, col2 = st.columns([6, 1])
                col1.markdown(
                    f'<div class="flex-container subcategory"><span class="label">{subcategory}</span></div>',
                    unsafe_allow_html=True,
                )
                if col2.button('🗑️', key=f'del_subcat_{category}-{subcategory}'):
                    _delete_subcategory(subcategory)

                rules = _get_rules(subcategory)
                if rules:
                    for rule in rules:
                        _, rule_col1, rule_col2 = st.columns([1, 5, 1])
                        rule_col1.markdown(
                            f'<div class="flex-container rule"><span class="label">{rule}</span></div>',
                            unsafe_allow_html=True,
                        )
                        if rule_col2.button('🗑️', key=f'del_rule_{category}-{subcategory}_{rule}'):
                            _delete_rule(subcategory, rule)
                else:
                    st.markdown('*No rules in this subcategory*')
                _, rule_col1, rule_col2 = st.columns([1, 5, 1])
                new_rule = rule_col1.text_input(
                    'New rule',
                    key=f'new_rule_{subcategory}',
                    label_visibility='collapsed',
                    placeholder='New rule',
                )
                if rule_col2.button('➕ Rule', key=f'add_rule_{category}-{subcategory}'):
                    _add_rule(new_rule, subcategory)
            col1, col2 = st.columns([6, 1])
            new_subcategory = col1.text_input(
                'New subcategory',
                key=f'new_subcat_{category}',
                label_visibility='collapsed',
                placeholder='New subcategory',
            )
            if col2.button('➕ Subcategory', key=f'add_subcat_{category}'):
                _add_subcategory(category, new_subcategory)
