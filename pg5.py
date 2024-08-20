import os
import streamlit as st
import mysql.connector
import pandas as pd

# MySQL connection setup

# Load database credentials from secrets.toml
DB_HOST = os.getenv("DATABASE_HOST")
DB_USER = os.getenv("DATABASE_USER")
DB_PASSWORD = os.getenv("DATABASE_PASSWORD")
DB_NAME = os.getenv("DATABASE_NAME")
DB_PORT = os.getenv("DATABASE_PORT")

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

# Fetch column names of a specific table


def fetch_columns(table_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"DESCRIBE {table_name}")
    columns = cursor.fetchall()
    conn.close()
    return [column[0] for column in columns]

# Fetch data from a specific table


def fetch_table_data(table_name):
    conn = get_db_connection()
    query = f"SELECT * FROM {table_name}"
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# Fetch list of all tables in the database


def fetch_all_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    conn.close()
    return [table[0].lower() for table in tables]

# Fetch department numbers from the Department table


def fetch_dept_numbers():
    conn = get_db_connection()
    query = "SELECT Dept_Code, Dept_no FROM Department"
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# Check if records already exist in the target table based on Student's Enrollment Number


def check_existing_records(table_name, records):
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholders = ', '.join(['%s'] * len(records))
    query = f"SELECT `Student's Enrollment Number` FROM {table_name} WHERE `Student's Enrollment Number` IN ({placeholders})"
    cursor.execute(query, records)
    existing_records = cursor.fetchall()
    conn.close()
    return [record[0] for record in existing_records]

# Append data to a specific table


def append_data_to_table(table_name, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Select only the required columns from the DataFrame
        data = data[['Name', 'Year of Enrollment',
                     "Student's Enrollment Number", 'Eligibility', 'Date of Enrollment']]

        # Format 'Date of Enrollment' column to 'mm/dd/yyyy' format
        def format_date(date_str):
            parts = date_str.split('-')
            if len(parts) == 3:
                return f"{parts[1]}/{parts[2]}/{parts[0]}"
            else:
                return date_str

        data['Date of Enrollment'] = data['Date of Enrollment'].apply(
            format_date)

        # Check for existing records to avoid duplicates
        existing_records = check_existing_records(
            table_name, data["Student's Enrollment Number"].tolist())
        data_to_append = data[~data["Student's Enrollment Number"].isin(
            existing_records)]

        if not data_to_append.empty:
            # Construct the SQL query for insertion
            columns = ', '.join(
                ['`' + col + '`' for col in data_to_append.columns])
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
    # Streamlit UI
    st.title("DSE Append Data")

    selected_table = 'all_dse'

    if st.button('Load Data from all_dse'):
        columns = fetch_columns(selected_table)
        if 'Department' in columns:
            df = fetch_table_data(selected_table)
            department_values = df['Department'].unique()
            all_tables = fetch_all_tables()

            # Debugging: Print all the tables
            st.write("All tables in the database:")
            st.write(all_tables)

            dept_numbers = fetch_dept_numbers()

            # Debugging: Print department numbers
            st.write("Department numbers:")
            st.write(dept_numbers)

            for dept_value in department_values:
                matching_dept = dept_numbers[dept_numbers['Dept_Code']
                                             == dept_value]
                if not matching_dept.empty:
                    Dept_no = matching_dept['Dept_no'].values[0]
                    dept_table_name = f"{Dept_no}_{dept_value}_SE".lower()

                    # Debugging: Print the constructed table name
                    st.write(f"Constructed table name: {dept_table_name}")

                    if dept_table_name in all_tables:
                        matching_data = df[df['Department'] == dept_value]
                        append_data_to_table(dept_table_name, matching_data)
                    else:
                        st.write(
                            f"Table {dept_table_name} does not exist in the database.")
                else:
                    st.write(
                        f"Department code {dept_value} not found in Department table.")


if __name__ == "__main__":
    main()
