import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from fuzzywuzzy import fuzz

# Load database credentials from secrets.toml
DB_HOST = st.secrets["database"]["DATABASE_HOST"]
DB_USER = st.secrets["database"]["DATABASE_USER"]
DB_PASSWORD = st.secrets["database"]["DATABASE_PASSWORD"]
DB_NAME = st.secrets["database"]["DATABASE_NAME"]
DB_PORT = st.secrets["database"]["DATABASE_PORT"]

# Create SQLAlchemy engine for MySQL connection
def get_sqlalchemy_engine():
    try:
        engine = create_engine(
            f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
            echo=False
        )
        return engine
    except Exception as err:
        st.error(f"Error creating SQLAlchemy engine: {err}")
        return None

# Function to fetch table names from the database
def get_table_names(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SHOW TABLES"))
        tables = [row[0] for row in result.fetchall()]
    return tables

# Function to fetch column names from a table
def get_column_names(engine, table_name):
    with engine.connect() as conn:
        result = conn.execute(text(f"SHOW COLUMNS FROM `{table_name}`"))
        columns = [row[0] for row in result.fetchall()]
    return columns

# Function to fetch data from a table
def get_table_data(engine, table_name):
    try:
        with engine.connect() as conn:
            query = f"SELECT * FROM `{table_name}`"
            data = pd.read_sql(query, conn)
        return data
    except Exception as e:
        st.error(f"Failed to fetch data from table {table_name}: {e}")
        return None

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

# Function to check existing records in the table
def check_existing_records(engine, table_name, column_name, values):
    with engine.connect() as conn:
        placeholders = ', '.join([':value'] * len(values))
        query = text(f"SELECT `{column_name}` FROM `{table_name}` WHERE `{column_name}` IN ({placeholders})")
        result = conn.execute(query, {'value': tuple(values)})
        existing_records = [row[0] for row in result.fetchall()]
    return set(existing_records)

# Function to append new data to the table
def append_data_to_table(engine, table_name, data):
    try:
        # Select only the required columns from the DataFrame
        data = data[['Name', 'Year of Enrollment', "Student's Enrollment Number", 'Eligibility', 'Date of Enrollment']]

        # Format 'Date of Enrollment' column to 'mm/dd/yyyy' format
        data['Date of Enrollment'] = pd.to_datetime(data['Date of Enrollment']).dt.strftime('%m/%d/%Y')

        # Check for existing records to avoid duplicates
        existing_records = check_existing_records(engine, table_name, "Student's Enrollment Number", data["Student's Enrollment Number"].tolist())
        data_to_append = data[~data["Student's Enrollment Number"].isin(existing_records)]

        if not data_to_append.empty:
            with engine.connect() as conn:
                # Construct the SQL query for insertion
                columns = ', '.join(['`' + col + '`' for col in data_to_append.columns])
                placeholders = ', '.join([f':{col}' for col in data_to_append.columns])
                sql = text(f"INSERT INTO `{table_name}` ({columns}) VALUES ({placeholders})")

                # Convert DataFrame to a list of dictionaries (to pass as params)
                data_dict = data_to_append.to_dict(orient='records')

                # Execute the query in batch
                conn.execute(sql, data_dict)
                conn.commit()
                st.write(f"Data appended to {table_name}")
        else:
            st.write(f"No new data to append to {table_name}")
    except Exception as e:
        st.error(f"Error appending data to {table_name}: {e}")

# Streamlit App Logic
def main():
    st.title("Department Comparison Tool")

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
            selected_excel_column = st.selectbox("Select a column from Excel file", excel_columns, key="excel_column_selectbox")

            # Step 3: Connect to SQLAlchemy engine and list tables
            engine = get_sqlalchemy_engine()
            if engine:
                tables = get_table_names(engine)
                selected_table = st.selectbox("Select a table from the database", tables, key="db_table_selectbox")

                if selected_table:
                    # Step 4: List columns from selected table
                    db_columns = get_column_names(engine, selected_table)
                    selected_db_column = st.selectbox("Select a column from the database table", db_columns, key="db_column_selectbox")

                    if selected_db_column:
                        # Step 5: Fetch data from the selected table
                        db_data = get_table_data(engine, selected_table)

                        # Step 6: Select department and create new table name
                        department_table_data = get_table_data(engine, "Department")
                        st.write("Department table columns:", department_table_data.columns)

                        if "Dept_name" in department_table_data.columns:
                            departments = department_table_data["Dept_name"].tolist()
                            selected_department = st.selectbox("Select a department", departments, key="department_selectbox")

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
                                if new_table_name:
                                    existing_records = check_existing_records(engine, new_table_name, selected_db_column, matched_df[selected_db_column].tolist())

                                    with engine.connect() as conn:
                                        # Create new table if it doesn't exist
                                        result = conn.execute(text(f"SHOW TABLES LIKE '{new_table_name}'"))
                                        if result.fetchone():
                                            st.warning(f"Table '{new_table_name}' already exists. Skipping table creation.")
                                        else:
                                            create_table_query = text(f"CREATE TABLE `{new_table_name}` LIKE `{selected_table}`")
                                            conn.execute(create_table_query)
                                            conn.commit()
                                            st.success(f"Table '{new_table_name}' created successfully.")

                                        # Insert matched records
                                        for _, row in matched_df.iterrows():
                                            if row[selected_db_column] not in existing_records:
                                                placeholders = ", ".join([f":{col}" for col in row.index])
                                                columns = ", ".join([f"`{col}`" for col in row.index])
                                                insert_query = text(f"INSERT INTO `{new_table_name}` ({columns}) VALUES ({placeholders})")
                                                conn.execute(insert_query, row.to_dict())

                                        conn.commit()
                                        st.success(f"Matched records have been saved to the new table: {new_table_name}")

                                    # Preview the new table
                                    new_table_data = get_table_data(engine, new_table_name)
                                    st.write(f"Preview of the new table '{new_table_name}':")
                                    st.write(new_table_data)

                        else:
                            st.error("The 'Dept_name' column does not exist in the 'department' table.")

if __name__ == "__main__":
    main()
