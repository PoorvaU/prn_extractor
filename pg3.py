

import streamlit as st
import pandas as pd
import mysql.connector
from fuzzywuzzy import process

# Function to connect to MySQL database
# Load database credentials from secrets.toml
DB_HOST = st.secrets["database"]["host"]
DB_USER = st.secrets["database"]["user"]
DB_PASSWORD = st.secrets["database"]["password"]
DB_NAME = st.secrets["database"]["database"]
DB_PORT = st.secrets["database"].get("port", 3306)



def connect_to_database():
    # Replace with your actual database credentials
    db_config = {
        'user': DB_USER,  # Change this to your MySQL username
        'password': DB_PASSWORD,  # Change this to your MySQL password
        'host': DB_HOST,
        'database': DB_NAME
    }
    try:
        connection = mysql.connector.connect(**db_config)
        return connection
    except mysql.connector.Error as err:
        st.error(f"Error: {err}")
        return None

# Function to list all tables in the database


def list_tables(connection):
    query = "SHOW TABLES"
    cursor = connection.cursor()
    cursor.execute(query)
    tables = cursor.fetchall()
    return [table[0] for table in tables]

# Function to list all columns in a given table


def list_columns(connection, table_name):
    query = f"SHOW COLUMNS FROM {table_name}"
    cursor = connection.cursor()
    cursor.execute(query)
    columns = cursor.fetchall()
    return [column[0] for column in columns]


def main():
    # Streamlit UI
    st.title("Eligibility Determiner")

    # Add a radio button for functionality selection
    option = st.radio(
        "Select functionality",
        ('List of dropout student', 'HOD list')
    )

    if option == 'List of dropout student':
        st.subheader("List of Dropout Students")

        # Step 1: Upload Excel file
        uploaded_file = st.file_uploader("Upload an Excel file", type=['xlsx'])
        if uploaded_file:
            workbook = pd.ExcelFile(uploaded_file)
            sheet_names = workbook.sheet_names
            selected_sheet = st.selectbox("Select a sheet", sheet_names)

            if selected_sheet:
                sheet_df = pd.read_excel(workbook, sheet_name=selected_sheet)
                excel_columns = sheet_df.columns.tolist()
                selected_excel_column = st.selectbox(
                    "Select a column from the Excel sheet", excel_columns)

                # Display column data for reference
                st.write(sheet_df[selected_excel_column])

                # Step 2: Connect to the database and list tables
                connection = connect_to_database()
                if connection:
                    tables = list_tables(connection)
                    selected_table = st.selectbox(
                        "Select a table from the database", tables)

                    if selected_table:
                        table_columns = list_columns(
                            connection, selected_table)
                        selected_db_column = st.selectbox(
                            "Select a column from the database table", table_columns)

                        # Step 3: Perform fuzzy matching and update the database
                        if st.button("Run Comparison and Update Database"):
                            table_df = pd.read_sql(
                                f"SELECT * FROM {selected_table}", connection)
                            matched_records = []
                            updated_records = []
                            unmatched_records = []

                            for excel_value in sheet_df[selected_excel_column]:
                                result = process.extractOne(
                                    excel_value, table_df[selected_db_column])
                                if result:
                                    best_match, score, _ = result  # Handle the returned index as well
                                    if score > 60:  # Adjust the threshold as needed
                                        matched_record = table_df[table_df[selected_db_column]
                                                                  == best_match]
                                        matched_records.append(
                                            (excel_value, best_match))
                                        updated_records.append(matched_record)
                                    else:
                                        unmatched_records.append(excel_value)

                            # Update the 'eligibility' column in the matched records
                            for record in updated_records:
                                name_to_update = record[selected_db_column].values[0]
                                query = f"UPDATE {selected_table} SET eligibility = 'not eligible' WHERE {selected_db_column} = '{name_to_update}'"
                                cursor = connection.cursor()
                                cursor.execute(query)
                                connection.commit()

                            # Display results
                            st.write("Matched Records:", matched_records)
                            st.write("Updated Records:", updated_records)
                            st.write("Unmatched Records:", unmatched_records)

                            st.write("Columns updated:", [selected_db_column])
                            cursor.close()
                            connection.close()
                else:
                    st.error(
                        "Failed to connect to the database. Please check your credentials and try again.")

    elif option == 'HOD list':
        st.subheader("HOD List")

        # Step 1: Upload Excel file
        uploaded_file = st.file_uploader("Upload an Excel file", type=['xlsx'])
        if uploaded_file:
            workbook = pd.ExcelFile(uploaded_file)
            sheet_names = workbook.sheet_names
            selected_sheet = st.selectbox("Select a sheet", sheet_names)

            if selected_sheet:
                sheet_df = pd.read_excel(workbook, sheet_name=selected_sheet)
                excel_column = st.selectbox(
                    "Select a column from the Excel sheet", sheet_df.columns.tolist())

                # Display column data for reference
                st.write(sheet_df[excel_column])

                # Step 2: Connect to the database and list tables
                connection = connect_to_database()
                if connection:
                    tables = list_tables(connection)
                    selected_table = st.selectbox(
                        "Select a table from the database", tables)

                    if selected_table:
                        table_columns = list_columns(
                            connection, selected_table)
                        db_column = st.selectbox(
                            "Select a column from the database table", table_columns)

                        # Step 3: Perform fuzzy matching and update the database
                        if st.button("Run Comparison and Update Database"):
                            table_df = pd.read_sql(
                                f"SELECT * FROM {selected_table}", connection)
                            matched_records = []
                            unmatched_records = []

                            # Prepare the set of Excel column values for fuzzy matching
                            excel_values_set = set(
                                sheet_df[excel_column].astype(str))

                            # Iterate through database records and compare with Excel values
                            for index, row in table_df.iterrows():
                                # Ensure db_value is a string
                                db_value = str(row[db_column])
                                result = process.extractOne(
                                    db_value, excel_values_set)

                                # Check if result is valid string
                                if result and isinstance(result[0], str):
                                    best_match, score = result  # Since we're only interested in best_match and score
                                    if score > 70:
                                        matched_records.append(
                                            (db_value, best_match))
                                        query = f"UPDATE {selected_table} SET eligibility = 'eligible' WHERE {db_column} = '{db_value}'"
                                        cursor = connection.cursor()
                                        cursor.execute(query)
                                        connection.commit()
                                    else:
                                        unmatched_records.append(db_value)
                                else:
                                    unmatched_records.append(db_value)

                            # Update the 'eligibility' column in the unmatched records
                            for db_value in unmatched_records:
                                query = f"UPDATE {selected_table} SET eligibility = 'not eligible' WHERE {db_column} = '{db_value}'"
                                cursor = connection.cursor()
                                cursor.execute(query)
                                connection.commit()

                            # Display results
                            st.write("Matched Records:", matched_records)
                            st.write("Unmatched Records:", unmatched_records)

                            cursor.close()
                            connection.close()
                else:
                    st.error(
                        "Failed to connect to the database. Please check your credentials and try again.")


if __name__ == "__main__":
    main()
