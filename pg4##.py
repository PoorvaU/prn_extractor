import streamlit as st
import pandas as pd
import mysql.connector
from fuzzywuzzy import fuzz, process

# Function to establish a connection to the MySQL database
# Load database credentials from secrets.toml
DB_HOST = st.secrets["database"]["host"]
DB_USER = st.secrets["database"]["user"]
DB_PASSWORD = st.secrets["database"]["password"]
DB_NAME = st.secrets["database"]["database"]

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

def fe_all_branchwise_comparison():
    # Step 1: Upload Excel file
    uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx"], key="fe_branchwise_uploader")
    if uploaded_file:
        df_excel = pd.read_excel(uploaded_file)
        st.write("Uploaded Excel file preview:")
        st.write(df_excel.head())

        # Step 2: Select columns from Excel file
        excel_columns = list(df_excel.columns)
        selected_excel_column = st.selectbox(
            "Select a column from Excel file to compare", excel_columns, key="excel_compare_column")
        selected_branch_column = st.selectbox(
            "Select a column from Excel file to segregate data (Branch)", excel_columns, key="excel_branch_column")

        # Step 3: Connect to MySQL and list tables
        conn = get_db_connection()
        if conn.is_connected():
            tables = get_table_names(conn)
            selected_table = st.selectbox(
                "Select a table from the database", tables, key="db_table_selectbox_fe_branchwise")

            if selected_table:
                # Step 4: List columns from selected table
                db_columns = get_column_names(conn, selected_table)
                selected_db_column = st.selectbox(
                    "Select a column from the database table to compare", db_columns, key="db_compare_column")

                if selected_db_column:
                    # Step 5: Fetch data from the selected table
                    db_data = get_table_data(conn, selected_table)

                    if st.button("Run Comparison", key="fe_branchwise_compare_button"):
                        # Step 6: Perform comparison and segregate data
                        department_table_data = get_table_data(conn, "Department")
                        st.write("Department table columns:", department_table_data.columns)

                        if "Dept_name" in department_table_data.columns:
                            matches = []
                            unmatched = []
                            for excel_value, branch in zip(df_excel[selected_excel_column].dropna(), df_excel[selected_branch_column]):
                                match = fuzzy_match(excel_value, db_data[selected_db_column].tolist())
                                if match:
                                    matched_record = db_data[db_data[selected_db_column] == match].iloc[0]
                                    matched_record['Branch'] = branch
                                    matches.append(matched_record)
                                else:
                                    unmatched.append(excel_value)

                            matched_df = pd.DataFrame(matches)
                            st.write("Matched records:")
                            st.write(matched_df)

                            if unmatched:
                                st.write("Unmatched records:")
                                st.write(unmatched)

                            # Step 7: Save matched records into new tables based on branch
                            for branch, group in matched_df.groupby('Branch'):
                                dept_info = department_table_data[department_table_data["Dept_Code"] == branch].iloc[0]
                                dept_no = dept_info["Dept_no"]
                                dept_code = dept_info["Dept_Code"]
                                new_table_name = f"{dept_no}_{dept_code}_FE"

                                cursor = conn.cursor()
                                create_table_query = f"CREATE TABLE IF NOT EXISTS `{new_table_name}` LIKE `{selected_table}`"
                                cursor.execute(create_table_query)
                                conn.commit()

                                existing_records = check_existing_records(new_table_name, selected_db_column, group[selected_db_column].tolist())

                                for _, row in group.iterrows():
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
                                st.write("Matched records:")
                                st.write(matched_df)

                                if unmatched:
                                    st.write("Unmatched records:")
                                    st.write(unmatched)

                                # Step 8: Save matched records into the new table
                                cursor = conn.cursor()
                                create_table_query = f"CREATE TABLE IF NOT EXISTS `{new_table_name}` LIKE `{selected_table}`"
                                cursor.execute(create_table_query)
                                conn.commit()

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
        fe_all_branchwise_comparison()
    else:
        st.write("Functionality for other departments is not yet implemented.")

if __name__ == "__main__":
    main()