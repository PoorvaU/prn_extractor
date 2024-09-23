import os
import streamlit as st
import pandas as pd
import mysql.connector
from datetime import datetime

# Load database credentials from secrets.toml
DB_HOST = st.secrets["database"]["DATABASE_HOST"]
DB_USER = st.secrets["database"]["DATABASE_USER"]
DB_PASSWORD = st.secrets["database"]["DATABASE_PASSWORD"]
DB_NAME = st.secrets["database"]["DATABASE_NAME"]
DB_PORT = int(st.secrets["database"]["DATABASE_PORT"])


def get_connection():
    """Establish a connection to the MySQL database."""
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

def fetch_departments():
    """Fetch all departments from the Department table."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Dept_no, Dept_code, Dept_name FROM Department")
    departments = cursor.fetchall()
    conn.close()
    return departments

def parse_date(date_str):
    """Parse date into a standard format."""
    if pd.isnull(date_str):
        return None
    formats = [
        "%b %d %Y %I:%M%p", "%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y",
        "%Y/%m/%d", "%d/%m/%Y", "%d-%b-%Y", "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S", "%m-%d-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime('%m/%d/%Y')
        except ValueError:
            continue
    return None

def check_existing_records(table_name, names):
    """Check for existing records in the database by Name."""
    conn = get_connection()
    cursor = conn.cursor()

    cleaned_names = [name for name in names if pd.notna(name)]
    if not cleaned_names:
        return set()

    placeholders = ', '.join(['%s'] * len(cleaned_names))
    query = f"SELECT `Name` FROM {table_name} WHERE `Name` IN ({placeholders})"
    cursor.execute(query, cleaned_names)
    existing_records = cursor.fetchall()
    conn.close()
    return set(record[0] for record in existing_records)

def main():
    st.title("PRN Generator")

    departments = fetch_departments()
    dept_names = ["All"] + [dept[2] for dept in departments]
    dept_name = st.selectbox("Department", dept_names)

    class_name = st.selectbox("Class", ["FE", "SE", "TE", "BE", "DSE"])

    if class_name == "FE":
        dept_name = "All"
    elif dept_name == "All" and class_name != "DSE":
        class_name = "FE"

    uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

    if uploaded_file:
        df = pd.read_excel(uploaded_file)

        selected_columns = st.multiselect("Select Columns", df.columns)

        add_year_of_enrollment = False
        if class_name == "FE" or dept_name == "All":
            add_year_of_enrollment = st.checkbox("Add Year of Enrollment Column")

        if add_year_of_enrollment:
            df["Year of Enrollment"] = "2023-24"

        column_order = selected_columns[:]
        if add_year_of_enrollment:
            column_order.insert(1, "Year of Enrollment")

        final_df = df[column_order]
        renamed_columns = ["Name", "Year of Enrollment", "Student's Enrollment Number", "Date of Enrollment", "Eligibility"]
        final_df.columns = renamed_columns[:len(final_df.columns)]

        if "Date of Enrollment" in final_df.columns:
            final_df["Date of Enrollment"] = final_df["Date of Enrollment"].apply(lambda x: parse_date(str(x)))

        final_df["Eligibility"] = "eligible"
        if dept_name == "All" and class_name == "DSE":
            final_df["Department"] = df["Department"]

        if st.button("Save to Database"):
            conn = get_connection()
            cursor = conn.cursor()

            # Determine table name based on department and class
            if dept_name == "All" and class_name == "FE":
                table_name = "all_fe_2023_24"
            elif dept_name == "All" and class_name == "DSE":
                table_name = "all_dse"
            else:
                dept_info = next((dept for dept in departments if dept[2] == dept_name), None)
                if dept_info:
                    dept_no, dept_code = dept_info[:2]
                    table_name = f"{dept_no}_{dept_code}_{class_name}"
                else:
                    table_name = f"{class_name}"

            # Create table if not exists
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                Name VARCHAR(255),
                `Year of Enrollment` VARCHAR(255),
                `Student's Enrollment Number` VARCHAR(255),
                `Date of Enrollment` VARCHAR(255),
                Eligibility VARCHAR(255)
            """
            if dept_name == "All" and class_name == "DSE":
                create_table_query += ", Department VARCHAR(255)"
            create_table_query += ")"

            cursor.execute(create_table_query)

            # Clean 'Student's Enrollment Number'
            final_df["Student's Enrollment Number"] = final_df["Student's Enrollment Number"].apply(
                lambda x: str(x).replace('.0', '') if pd.notna(x) else None
            )

            # Check for existing records
            names = final_df["Name"].tolist()
            existing_names = check_existing_records(table_name, names)

            # Insert data, avoiding duplicates
            for _, row in final_df.iterrows():
                row_values = [None if pd.isna(val) else val for val in row]

                if row["Name"] not in existing_names:
                    insert_query = f"""
                    INSERT INTO {table_name} (Name, `Year of Enrollment`, `Student's Enrollment Number`, `Date of Enrollment`, Eligibility
                    """
                    if dept_name == "All" and class_name == "DSE":
                        insert_query += ", Department"
                    insert_query += ") VALUES (%s, %s, %s, %s, %s"
                    if dept_name == "All" and class_name == "DSE":
                        insert_query += ", %s"
                    insert_query += ")"
                    cursor.execute(insert_query, row_values)
                    existing_names.add(row["Name"])  # Update existing names set

            conn.commit()
            conn.close()
            st.success(f"Data saved to {table_name} table in the University database.")

if __name__ == "__main__":
    main()
