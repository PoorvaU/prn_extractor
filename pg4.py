import os
import streamlit as st
import pandas as pd
import mysql.connector
from fuzzywuzzy import fuzz, process

# Function to establish a connection to the MySQL database
# Load database credentials from secrets.toml
DB_HOST = st.secrets["database"]["DATABASE_HOST"]
DB_USER = st.secrets["database"]["DATABASE_USER"]
DB_PASSWORD = st.secrets["database"]["DATABASE_PASSWORD"]
DB_NAME = st.secrets["database"]["DATABASE_NAME"]
DB_PORT = int(st.secrets["database"]["DATABASE_PORT"])

st.write("Host:", DB_HOST)
st.write("User:", DB_USER)
st.write("Database Name:", DB_NAME)


def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

# Function to fetch table names from the database
def get_table_names(conn):
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    return [table[0] for table in tables]

# Function to fetch column names from a table
def get_column_names(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"SHOW COLUMNS FROM {table_name}")
    columns = cursor.fetchall()
    return [column[0] for column in columns]

# Function to fetch data from a table
def get_table_data(conn, table_name):
    return pd.read_sql(f"SELECT * FROM `{table_name}`", conn)

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

def check_existing_records(table_name, column_name, values):
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholders = ', '.join(['%s'] * len(values))
    query = f"SELECT `{column_name}` FROM {table_name} WHERE `{column_name}` IN ({placeholders})"
    cursor.execute(query, values)
    existing_records = cursor.fetchall()
    conn.close()
    return set([record[0] for record in existing_records])

def append_data_to_table(table_name, data):
    conn = get_db_connection()
    cursor = conn.cursor()
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
        existing_records = check_existing_records(table_name, "Student's Enrollment Number", data["Student's Enrollment Number"].tolist())
        data_to_append = data[~data["Student's Enrollment Number"].isin(existing_records)]

        if not data_to_append.empty:
            # Construct the SQL query for insertion
            columns = ', '.join(['`' + col + '`' for col in data_to_append.columns])
            placeholders = ', '.join(['%s'] * len(data_to_append.columns))
            sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

            # Convert DataFrame to list of tuples
            data_values = [tuple(row) for row in data_to_append.values]

            # Execute the query
            cursor.executemany(sql, data_values)
            conn.commit()
            st.write(f"Data appended to {table_name}")
        else:
            st.write(f"No new data to append to {table_name}")
    except Exception as e:
        st.write(f"Error appending data to {table_name}: {e}")
    finally:
        conn.close()



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

            # Step 3: Connect to MySQL and list tables
            conn = get_db_connection()
            if conn.is_connected():
                tables = get_table_names(conn)
                selected_table = st.selectbox(
                    "Select a table from the database", tables, key="db_table_selectbox")

                if selected_table:
                    # Step 4: List columns from selected table
                    db_columns = get_column_names(conn, selected_table)
                    selected_db_column = st.selectbox(
                        "Select a column from the database table", db_columns, key="db_column_selectbox")

                    if selected_db_column:
                        # Step 5: Fetch data from the selected table
                        db_data = get_table_data(conn, selected_table)

                        # Step 6: Select department and create new table name
                        department_table_data = get_table_data(conn, "Department")
                        st.write("Department table columns:",
                                 department_table_data.columns)

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
                                cursor = conn.cursor()
                                cursor.execute(f"SHOW TABLES LIKE '{new_table_name}'")
                                if cursor.fetchone():
                                    st.warning(f"Table '{new_table_name}' already exists. Skipping table creation.")
                                else:
                                    create_table_query = f"CREATE TABLE `{new_table_name}` LIKE `{selected_table}`"
                                    cursor.execute(create_table_query)
                                    conn.commit()
                                    st.success(f"Table '{new_table_name}' created successfully.")

                                
                                   
                                # create_table_query = f"CREATE TABLE IF NOT EXISTS `{new_table_name}` LIKE `{selected_table}`"
                                # cursor.execute(create_table_query)
                                # conn.commit()

                                existing_records = check_existing_records(new_table_name, selected_db_column, matched_df[selected_db_column].tolist())

                                for _, row in matched_df.iterrows():
                                    if row[selected_db_column] not in existing_records:
                                        placeholders = ", ".join(["%s"] * len(row))
                                        columns = ", ".join([f"`{col}`" for col in row.index])
                                        insert_query = f"INSERT INTO `{new_table_name}` ({columns}) VALUES ({placeholders})"
                                        cursor.execute(insert_query, tuple(row))
                                        conn.commit()

                                st.success(f"Matched records have been saved to the new table: {new_table_name}")

                                # Preview the new table
                                new_table_data = get_table_data(conn, new_table_name)
                                st.write(f"Preview of the new table '{new_table_name}':")
                                st.write(new_table_data)

                        else:
                            st.error("The 'Dept_name' column does not exist in the 'department' table.")

                    conn.close()
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

            # Step 3: Connect to MySQL and list tables
            conn = get_db_connection()
            if conn.is_connected():
                tables = get_table_names(conn)
                selected_table = st.selectbox("Select a table from the database", tables, key="db_table_selectbox_branchwise")

                if selected_table:
                    # Step 4: List columns from selected table
                    db_columns = get_column_names(conn, selected_table)
                    selected_db_column = st.selectbox("Select a column from the database table", db_columns, key="db_column_selectbox_branchwise")

                    if selected_db_column:
                        # Step 5: Fetch data from the selected table
                        db_data = get_table_data(conn, selected_table)

                        # Step 6: Get department data and map to Excel file's categorization column
                        department_table_data = get_table_data(conn, "department")
                        st.write("Department table columns:", department_table_data.columns)

                        if "Dept_name" in department_table_data.columns and "Dept_no" in department_table_data.columns and "Dept_Code" in department_table_data.columns:
                            # Unique department values from selected table
                            branches = df_excel[selected_categorization_column].unique()

                            for branch in branches:
                                dept_info = department_table_data[department_table_data["Dept_Code"] == branch]

                                if not dept_info.empty:
                                    dept_info = dept_info.iloc[0]
                                    dept_no = dept_info["Dept_no"]
                                    Dept_Code = dept_info["Dept_Code"]
                                    new_table_name = f"{dept_no}_{Dept_Code}_FE"

                                    # Filter data for the current department
                                    branch_data = df_excel[df_excel[selected_categorization_column] == branch]

                                    # Perform fuzzy matching
                                    matches = []
                                    unmatched = []
                                    for excel_value in branch_data[selected_excel_column].dropna():
                                        match = fuzzy_match(excel_value, db_data[selected_db_column].tolist())
                                        if match:
                                            matched_record = db_data[db_data[selected_db_column] == match].iloc[0]
                                            matches.append(matched_record)
                                        else:
                                            unmatched.append(excel_value)

                                    matched_df = pd.DataFrame(matches)

                                    if not matched_df.empty:
                                        st.write(f"Matched records for {Dept_Code}:")
                                        st.write(matched_df)

                                        # Step 7: Save matched records into the new table
                                        cursor = conn.cursor()

                                        # Check if table already exists
                                        cursor.execute(f"SHOW TABLES LIKE '{new_table_name}'")
                                        if cursor.fetchone():
                                            st.warning(f"Table '{new_table_name}' already exists. Skipping table creation.")

                                        else:
                                            # Create new table if it doesn't exist
                                            create_table_query = f"CREATE TABLE `{new_table_name}` LIKE `{selected_table}`"
                                            cursor.execute(create_table_query)
                                            conn.commit()
                                            st.success(f"Table '{new_table_name}' created successfully.")

                                        # Insert matched records into the new table
                                        existing_records = check_existing_records(new_table_name, selected_db_column, matched_df[selected_db_column].tolist())

                                        for _, row in matched_df.iterrows():
                                            if row[selected_db_column] not in existing_records:
                                                placeholders = ", ".join(["%s"] * len(row))
                                                columns = ", ".join([f"`{col}`" for col in row.index])
                                                insert_query = f"INSERT INTO `{new_table_name}` ({columns}) VALUES ({placeholders})"
                                                cursor.execute(insert_query, tuple(row))
                                                conn.commit()

                                        st.success(f"Matched records have been saved to the new table: {new_table_name}")

                                        # Preview the new table
                                        new_table_data = get_table_data(conn, new_table_name)
                                        st.write(f"Preview of the new table '{new_table_name}':")
                                        st.write(new_table_data)

                                    else:
                                        st.write(f"No matched records for {Dept_Code}.")

                                    if unmatched:
                                        st.write(f"Unmatched records for {Dept_Code}:")
                                        st.write(unmatched)

                                else:
                                    st.error(f"Selected department {branch} does not exist in the 'department' table.")

                        else:
                            st.error("The 'Dept_name', 'Dept_no', or 'Dept_Code' column does not exist in the 'department' table.")

                    conn.close()
                else:
                    st.error("Failed to connect to the database.")
    else:
        st.write("Functionality for other departments is not yet implemented.")

if __name__ == "__main__":
    main()