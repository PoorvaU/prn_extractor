import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text 
from fuzzywuzzy import fuzz, process

# Load database credentials from secrets.toml
DB_HOST = st.secrets["database"]["DATABASE_HOST"]
DB_USER = st.secrets["database"]["DATABASE_USER"]
DB_PASSWORD = st.secrets["database"]["DATABASE_PASSWORD"]
DB_NAME = st.secrets["database"]["DATABASE_NAME"]
DB_PORT = int(st.secrets["database"]["DATABASE_PORT"])

# Create SQLAlchemy engine
engine = create_engine(f'mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}')

# Function to fetch table names from the database
def get_table_names(engine):
    with engine.connect() as connection:
        result = connection.execute(text("SHOW TABLES"))
        tables = [row[0] for row in result]
    return tables

# Function to fetch column names from a table
def get_column_names(engine, table_name):
    with engine.connect() as connection:
        result = connection.execute(text(f"SHOW COLUMNS FROM {table_name}"))
        columns = [row[0] for row in result]
    return columns

# Function to fetch data from a table
def get_table_data(engine, table_name):
    with engine.connect() as connection:
        return pd.read_sql(text(f"SELECT * FROM {table_name}"), connection)

# Function to perform fuzzy matching and find the closest match
def fuzzy_match(value, choices):
    best_match = None
    highest_ratio = -1

    value_str = str(value).lower()  # Ensure value is a string

    for choice in choices:
        choice_str = str(choice).lower()  # Ensure choice is a string
        ratio = fuzz.token_sort_ratio(value_str, choice_str)
        if ratio > highest_ratio:
            highest_ratio = ratio
            best_match = choice

        # Check for partial matches or substring matches
        for part in value_str.split():
            if part in choice_str:
                ratio = 100  # You can adjust this threshold as needed
                if ratio > highest_ratio:
                    highest_ratio = ratio
                    best_match = choice

    return best_match if highest_ratio >= 70 else None

def check_existing_records(engine, table_name, column_name, values):
    with engine.connect() as connection:
        placeholders = ', '.join(['%s'] * len(values))
        query = f"SELECT {column_name} FROM {table_name} WHERE {column_name} IN ({placeholders})"
        result = connection.execute(query, values)
        existing_records = result.fetchall()
    return set(record[0] for record in existing_records)

def append_data_to_table(engine, table_name, data):
    with engine.connect() as connection:
        try:
            # Select only the required columns from the DataFrame
            data = data[['Name', 'Year of Enrollment', "Student's Enrollment Number", 'Eligibility', 'Date of Enrollment']]

            # Format 'Date of Enrollment' column to 'mm/dd/yyyy' format
            def format_date(date_str):
                parts = date_str.split('-')
                if len(parts) == 3:
                    return f"{parts[1]}/{parts[2]}/{parts[0]}"
                else:
                    return date_str

            data['Date of Enrollment'] = data['Date of Enrollment'].apply(format_date)

            # Check for existing records to avoid duplicates
            existing_records = check_existing_records(engine, table_name, "Student's Enrollment Number", data["Student's Enrollment Number"].tolist())
            data_to_append = data[~data["Student's Enrollment Number"].isin(existing_records)]

            if not data_to_append.empty:
                # Construct the SQL query for insertion
                columns = ', '.join([f'`{col}`' for col in data_to_append.columns])
                placeholders = ', '.join(['%s'] * len(data_to_append.columns))
                sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

                # Convert DataFrame to list of tuples
                data_values = [tuple(row) for row in data_to_append.values]

                # Execute the query
                connection.execute(sql, data_values)
                st.write(f"Data appended to {table_name}")
            else:
                st.write(f"No new data to append to {table_name}")
        except Exception as e:
            st.write(f"Error appending data to {table_name}: {e}")

def main():
    # Streamlit app
    st.title("Department Comparison Tool")

    # Radio button for selecting department
    selected_department = st.radio("Select Department", ["FE Department", "FE - All Branchwise", "Other Departments"])

    if selected_department == "FE Department":
        # Step 1: Upload Excel file
        uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx"])
        if uploaded_file:
            df_excel = pd.read_excel(uploaded_file)
            st.write("Uploaded Excel file preview:")
            st.write(df_excel.head())

            # Step 2: Select column from Excel file
            excel_columns = list(df_excel.columns)
            selected_excel_column = st.selectbox(
                "Select a column from Excel file", excel_columns, key="excel_column_selectbox")

            # Step 3: List tables
            tables = get_table_names(engine)
            selected_table = st.selectbox(
                "Select a table from the database", tables, key="db_table_selectbox")

            if selected_table:
                # Step 4: List columns from selected table
                db_columns = get_column_names(engine, selected_table)
                selected_db_column = st.selectbox(
                    "Select a column from the database table", db_columns, key="db_column_selectbox")

                if selected_db_column:
                    # Step 5: Fetch data from the selected table
                    db_data = get_table_data(engine, selected_table)

                    # Step 6: Select department and create new table name
                    department_table_data = get_table_data(engine, "Department")
                    st.write("Department table columns:", department_table_data.columns)

                    if "Dept_name" in department_table_data.columns:
                        departments = department_table_data["Dept_name"].tolist()
                        selected_department = st.selectbox(
                            "Select a department", departments, key="department_selectbox")

                        # Find the corresponding Dept_no and Dept_Code
                        dept_info = department_table_data[department_table_data["Dept_name"] == selected_department].iloc[0]
                        dept_no = dept_info["Dept_no"]
                        Dept_Code = dept_info["Dept_Code"]
                        new_table_name = f"{dept_no}_{Dept_Code}_FE"

                        if st.button("Run Comparison"):
                            # Step 7: Perform comparison and create a new table with matched records
                            matches = []
                            unmatched = []
                            for excel_value in df_excel[selected_excel_column].dropna():
                                match = fuzzy_match(excel_value, db_data[selected_db_column].tolist())
                                if match:
                                    matched_record = db_data[db_data[selected_db_column] == match].iloc[0]
                                    matches.append(matched_record)
                                else:
                                    unmatched.append(excel_value)

                            matched_df = pd.DataFrame(matches)
                            if not matched_df.empty:
                                st.write("Matched records:")
                                st.write(matched_df)

                            if unmatched:
                                st.write("Unmatched records:")
                                st.write(unmatched)

                            # Step 8: Save matched records into the new table
                            with engine.connect() as connection:
                                cursor = connection.execution_options(autocommit=True).execute
                                cursor.execute(f"SHOW TABLES LIKE '{new_table_name}'")
                                if cursor.fetchone():
                                    st.warning(f"Table '{new_table_name}' already exists. Skipping table creation.")
                                else:
                                    create_table_query = f"CREATE TABLE {new_table_name} LIKE {selected_table}"
                                    cursor.execute(create_table_query)
                                    st.success(f"Table '{new_table_name}' created successfully.")

                                existing_records = check_existing_records(engine, new_table_name, selected_db_column, matched_df[selected_db_column].tolist())

                                for _, row in matched_df.iterrows():
                                    if row[selected_db_column] not in existing_records:
                                        placeholders = ", ".join(["%s"] * len(row))
                                        columns = ", ".join([f"{col}" for col in row.index])
                                        insert_query = f"INSERT INTO {new_table_name} ({columns}) VALUES ({placeholders})"
                                        cursor.execute(insert_query, tuple(row))

                                st.success(f"Matched records have been saved to the new table: {new_table_name}")

                                # Preview the new table
                                new_table_data = get_table_data(engine, new_table_name)
                                st.write(f"Preview of the new table '{new_table_name}':")
                                st.write(new_table_data)

                    else:
                        st.error("The 'Dept_name' column does not exist in the 'department' table.")

            else:
                st.error("Failed to connect to the database.")

    elif selected_department == "FE - All Branchwise":
        # Step 1: Upload Excel file
        uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx"])
        if uploaded_file:
            df_excel = pd.read_excel(uploaded_file)
            st.write("Uploaded Excel file preview:")
            st.write(df_excel.head())

            # Step 2: Select columns from Excel file
            excel_columns = list(df_excel.columns)
            selected_excel_column = st.selectbox("Select a column for comparison from Excel file", excel_columns, key="excel_column_selectbox_comparison")
            selected_categorization_column = st.selectbox("Select a column for categorization from Excel file", excel_columns, key="excel_column_selectbox_categorization")

            # Step 3: List tables
            tables = get_table_names(engine)
            selected_table = st.selectbox("Select a table from the database", tables, key="db_table_selectbox_all_branchwise")

            if selected_table:
                # Step 4: List columns from selected table
                db_columns = get_column_names(engine, selected_table)
                selected_db_column = st.selectbox("Select a column from the database table", db_columns, key="db_column_selectbox_all_branchwise_db_column_select")

                if selected_db_column:
                    # Step 5: Fetch data from the selected table
                    db_data = get_table_data(engine, selected_table)

                    # Step 6: Perform comparison and categorize results
                    matches = []
                    unmatched = []
                    categorized = {}

                    for excel_value in df_excel[selected_excel_column].dropna():
                        match = fuzzy_match(excel_value, db_data[selected_db_column].tolist())
                        if match:
                            matched_record = db_data[db_data[selected_db_column] == match].iloc[0]
                            matches.append(matched_record)
                        else:
                            unmatched.append(excel_value)

                    matched_df = pd.DataFrame(matches)

                    # Categorize based on selected categorization column
                    if not matched_df.empty:
                        for _, row in matched_df.iterrows():
                            category = row[selected_categorization_column] if selected_categorization_column in row else "Uncategorized"
                            if category not in categorized:
                                categorized[category] = []
                            categorized[category].append(row)

                        # Display categorized results
                        for category, records in categorized.items():
                            st.write(f"Category: {category}")
                            st.write(pd.DataFrame(records))

                    if unmatched:
                        st.write("Unmatched records:")
                        st.write(unmatched)

    else:
        st.error("No department selected.")

if __name__ == "__main__":
    main()
