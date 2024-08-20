
import streamlit as st
import pandas as pd
import mysql.connector
from datetime import datetime

# Load database credentials from secrets.toml
DB_HOST = st.secrets["database"]["host"]
DB_USER = st.secrets["database"]["user"]
DB_PASSWORD = st.secrets["database"]["password"]
DB_NAME = st.secrets["database"]["database"]
DB_PORT = st.secrets["database"].get("port", 3306)



def get_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )


def fetch_departments():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Dept_no, Dept_code, Dept_name FROM Department")
    departments = cursor.fetchall()
    conn.close()
    return departments


def parse_date(date_str):
    if pd.isnull(date_str):
        return None
    formats = ["%b %d %Y %I:%M%p", "%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y",
               "%d-%b-%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%m-%d-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime('%m/%d/%Y')
        except ValueError:
            continue
    return None


def check_existing_records(table_name, names):
    conn = get_connection()
    cursor = conn.cursor()

    # Filter out NaN values from names
    cleaned_names = [name for name in names if pd.notna(name)]
    placeholders = ', '.join(['%s'] * len(cleaned_names))

    query = f"SELECT `Name` FROM {table_name} WHERE `Name` IN ({placeholders})"
    cursor.execute(query, cleaned_names)
    existing_records = cursor.fetchall()

    conn.close()
    return set([record[0] for record in existing_records])


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
        st.write("Uploaded File Columns:")
        st.dataframe(df.columns)

        selected_columns = st.multiselect("Select Columns", df.columns)

        add_year_of_enrollment = False

        if class_name == "FE" or dept_name == "All":
            add_year_of_enrollment = st.checkbox(
                "Add Year of Enrollment Column")

        if add_year_of_enrollment:
            df["Year of Enrollment"] = "2023-24"

        column_order = selected_columns[:]
        if add_year_of_enrollment:
            column_order.insert(1, "Year of Enrollment")

        final_df = df[column_order]

        renamed_columns = ["Name", "Year of Enrollment",
                           "Student's Enrollment Number", "Date of Enrollment", "Eligibility"]
        final_column_names = renamed_columns[:len(final_df.columns)]
        final_df.columns = final_column_names

        if "Date of Enrollment" in final_df.columns:
            final_df["Date of Enrollment"] = final_df["Date of Enrollment"].apply(
                lambda x: parse_date(str(x)))

        final_df["Eligibility"] = "eligible"

        if dept_name == "All" and class_name == "DSE":
            final_df["Department"] = df["Department"]

        st.write("Selected Data:")
        st.dataframe(final_df)

        if st.button("Save to Database"):
            conn = get_connection()
            cursor = conn.cursor()

            if dept_name == "All" and class_name == "FE":
                table_name = "all_fe_2023_24"
            elif dept_name == "All" and class_name == "DSE":
                table_name = "all_dse"
            else:
                dept_info = next(
                    (dept for dept in departments if dept[2] == dept_name), None)
                if dept_info:
                    dept_no, dept_code = dept_info[:2]
                    table_name = f"{dept_no}_{dept_code}_{class_name}"
                else:
                    table_name = f"{class_name}"

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

            final_df["Student's Enrollment Number"] = final_df["Student's Enrollment Number"].apply(
                lambda x: str(x).replace('.0', '') if pd.notna(x) else None)

            names = final_df["Name"].tolist()
            existing_names = check_existing_records(table_name, names)

            # Debug: Print existing Names
            print(f"Existing Names: {existing_names}")

            for _, row in final_df.iterrows():
                row_values = [None if pd.isna(val) else val for val in row]

                # Debug: Print row Name and check if it exists
                print(f"Checking Name: {row['Name']}")

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
                    # Add the new Name to the set of existing Names
                    existing_names.add(row["Name"])
                else:
                    # Debug: Print message if record exists
                    print(
                        f"Record with Name {row['Name']} already exists. Skipping insertion.")

            conn.commit()
            conn.close()
            st.success(
                f"Data saved to {table_name} table in the University database.")


if __name__ == "__main__":
    main()
