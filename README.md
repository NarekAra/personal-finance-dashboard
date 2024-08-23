# Personal Finance Dashboard 👋

**Take Control of Your Finances.**

This is a Streamlit application that provides a comprehensive dashboard for visualizing and analyzing personal finance data. The application allows users to upload their transaction data (e.g., from a bank statement) and generates interactive visualizations and insights based on the data.

## Pages

### Categorizer
The Categorizer allows users to categorize their financial transactions by uploading transaction data and a configuration file. It automatically assigns categories and subcategories based on the provided rules, displays the categorized transactions in an interactive grid, and enables users to manually edit or download the categorized data.

### Dashboard
The Dashboard lets users upload transaction data from Excel files. It displays balance trends over time for different sources such as bank accounts and credit cards using graphs and tiles. It also provides insights into spending per category using bar graphs. Additionally, users can set financial goals, like limiting travel expenses, and track their progress with a heatmap.


The application's behavior and settings can be customized the dasboard settings.

## Folder Structure
```
personal-finance-dashboard/
├── app_pages/                          # Directory for all the pages
│   ├── categorize_page.py
│   ├── dashboard_page.py
│   ├── dashboard_settings.py
│   └── manage_account.py
├── example_resources/                  # Directory for storing data files for demo
│   ├── categorized/                    # Data for the dashboard
│   │   ├── data_structure.xlsx
│   │   └── transactions.xlsx
│   └── raw/                            # Data for the categorizer
│       ├── categories_mapping.yml
│       ├── data_structure.xlsx
│       └── transactions.xlsx
├── utils/                              # Utility functions for all plots and calculations
│   ├── app_utils.py
│   ├── calculate_utils.py
│   ├── constants.py                    
│   ├── dashboard_utils.py
│   ├── data_utils.py
│   ├── firebasehandler.py
│   ├── parse_data.py
│   ├── plot_dashboard_utils.py
│   └── plots.py                        
├── app.py                              # Main Streamlit application file
├── default_dashboard.yml               # Default settings of the dashboard
├── main.css                            # CSS
├── requirements.txt                    # Python dependencies
├── .gitignore
├── README.md
├── requirements.txt
```

## Getting Started

1. Clone the repository:
```
$ git clone https://github.com/NarekAra/personal-finance-dashboard.git
```
2. Install the required dependencies:
```
$ pip install -r requirements.txt
```

3. Run the Streamlit application:
```
$ streamlit run app.py
```

## Contributing

Contributions to this project are welcome, especially the ones mentioned in the roadmap. If you find any issues or have suggestions for improvements, please open an issue or submit a pull request.

## Roadmap (not in order)
- [x] Allow users to log in (firebase)
- [x] Instead of providing a .yml config, allow users to do this through the UI (subject to users being able to log in)
- [ ] Figure out if it is plausible to get data from banks API, not through an excel.
- [ ] Can GPT help with categorization?
- [ ] Other plots? Let users choose their own plots? Make it more modular.
- [ ] Make the UI more consistant (e.g. colours)
- [ ] Make seperate dashboard to keep track of investments
- [ ] Allow users to add assets (not only cash-flow) like real-estate
- [ ] Allow users to keep track of their debt
- [ ] Look forward: projected income/outcome in the future
- [ ] Allow users to chat with their transactions
- ...

## Changelog
- 01/06/2024: First version. Added the dashboard
- 02/06/2024: Added the transaction categorizer
- 05/06/2024: Added support for financial goals
- 15/08/2024: Allow changing the config in the UI
- 23/08/2024: Allow users to log in