

import streamlit as st
import pandas as pd
import mysql.connector
from mysql.connector import Error
from io import BytesIO
import base64

# MySQL database connection

# Load database credentials from secrets.toml
DB_HOST = st.secrets["database"]["host"]
DB_USER = st.secrets["database"]["user"]
DB_PASSWORD = st.secrets["database"]["password"]
DB_NAME = st.secrets["database"]["database"]


def create_connection():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        if conn.is_connected():
            return conn
    except Error as e:
        st.error(f"Error: '{e}'")
        return None


def fetch_departments(conn):
    query = "SELECT Dept_name, Dept_Code, Dept_no FROM Department"
    return pd.read_sql(query, conn)


def fetch_tables(conn, Dept_no, Dept_Code):
    query = f"""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = '{DB_NAME}' AND table_name LIKE '{Dept_no}_{Dept_Code}_%'
    """
    tables_df = pd.read_sql(query, conn)
    tables_list = tables_df['TABLE_NAME'].tolist()

    # Sort tables in the order fe, se, te, be
    sorted_tables = sorted(tables_list, key=lambda x: int(x.split(
        '_')[-1].replace('fe', '1').replace('se', '2').replace('te', '3').replace('be', '4')))

    st.write(tables_df)  # Debugging output to check the returned DataFrame
    return sorted_tables


def create_and_download_excel(sheets_dict, file_name):
    excel_file_bytes = BytesIO()
    with pd.ExcelWriter(excel_file_bytes, engine='xlsxwriter') as writer:
        for sheet_name, df in sheets_dict.items():
            df = df.fillna('') 
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            workbook = writer.book
            worksheet = writer.sheets[sheet_name]
            header_format = workbook.add_format(
                {'bold': True, 'font_size': 12, 'font_name': 'Times New Roman', 'text_wrap': True, 'valign': 'vcenter'})
            cell_format = workbook.add_format(
                {'font_size': 12, 'font_name': 'Times New Roman', 'text_wrap': True, 'valign': 'vcenter'})
            red_fill = workbook.add_format({'bg_color': '#FF0000'})
            cell_format_wrap_text = workbook.add_format(
                {'text_wrap': True, 'font_size': 12, 'font_name': 'Times New Roman', 'valign': 'vcenter'})

            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            for row_num in range(1, len(df) + 1):
                for col_num, value in enumerate(df.iloc[row_num - 1]):
                    if df.columns[col_num] == "Student's Enrollment Number":
                        worksheet.write_string(
                            row_num, col_num, str(value), cell_format)
                    else:
                        worksheet.write(row_num, col_num, value, cell_format)
                    if pd.isna(value) and df.columns[col_num] == "Student's Enrollment Number":
                        worksheet.write_blank(row_num, col_num, None, red_fill)
            worksheet.set_default_row(30)

            for i in range(4):
                max_len = max(df.iloc[:, i].astype(
                    str).apply(len).max(), len(df.columns[i]))
                worksheet.set_column(i, i, max_len + 2)

            if len(df.columns) > 4:
                worksheet.set_column(4, len(df.columns) - 1,
                                     None, None, {'hidden': True})

    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{base64.b64encode(excel_file_bytes.getvalue()).decode()}" download="{file_name}.xlsx">Download {file_name}.xlsx</a>'
    st.markdown(href, unsafe_allow_html=True)

def fetch_year_institute_wise_tables(conn, class_name):
    try:
        query = f"""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = '{DB_NAME}' 
        AND table_name LIKE '%_{class_name.lower()}'
        """
        tables_df = pd.read_sql(query, conn)
        tables_list = tables_df['TABLE_NAME'].tolist()
        return tables_list
    except Error as e:
        st.error(f"Error fetching tables: {e}")
        return []
    
def fetch_all_tables(conn):
    try:
        query = f"SHOW TABLES FROM {DB_NAME}"
        tables_df = pd.read_sql(query, conn)
        tables_list = tables_df.iloc[:, 0].tolist()
        return tables_list
    except Error as e:
        st.error(f"Error fetching tables: {e}")
        return []



def main():
    st.title("Report Generator")

    export_type = st.radio(
        "Select Export Type",
        ('Institute wise', 'Department wise', 'Individual', 'Year Institute Wise', 'Year Department Wise')
    )

    conn = create_connection()
    if conn:
        departments_df = fetch_departments(conn)
        dept_names = departments_df['Dept_name'].tolist()

        if export_type == 'Institute wise' or export_type == 'Department wise':
            selected_dept_name = st.selectbox("Select Department", dept_names)
            if selected_dept_name:
                dept_info = departments_df[departments_df['Dept_name']
                                           == selected_dept_name].iloc[0]
                Dept_no = dept_info['Dept_no']
                Dept_Code = dept_info['Dept_Code']
                tables = fetch_tables(conn, Dept_no, Dept_Code)

                if export_type == 'Institute wise':
                    if st.button("Export"):
                        combined_data = []
                        for table in tables:
                            df = pd.read_sql(f"SELECT * FROM {table}", conn)
                            if not df.empty:
                                combined_data.append(df)
                        if combined_data:
                            combined_df = pd.concat(
                                combined_data, ignore_index=True)
                            create_and_download_excel(
                                {'Combined Data': combined_df}, f"{Dept_no}_{Dept_Code}_Institute_Wise")

                elif export_type == 'Department wise':
                    if st.button("Export"):
                        sheets_dict = {}
                        for table in tables:
                            class_name = table.split('_')[-1]
                            df = pd.read_sql(f"SELECT * FROM {table}", conn)
                            if not df.empty:
                                sheets_dict[class_name] = df
                        if sheets_dict:
                            create_and_download_excel(
                                sheets_dict, f"{Dept_no}_{Dept_Code}_Department_Wise")
                            
        elif export_type == 'Year Institute Wise':
            class_name = st.selectbox("Select CLASS", ['FE', 'SE', 'TE', 'BE'])
            if class_name:
                tables = fetch_year_institute_wise_tables(conn, class_name)
                if st.button("Export"):
                    if tables:
                        combined_data = []
                        for table in tables:
                            df = pd.read_sql(f"SELECT * FROM {table}", conn)
                            if not df.empty:
                                combined_data.append(df)
                        if combined_data:
                            combined_df = pd.concat(combined_data, ignore_index=True)
                            create_and_download_excel({'Combined Data': combined_df}, f"{class_name}_Year_Institute_Wise")
                    else:
                        st.warning("No tables found for the selected class.")

        elif export_type == 'Year Department Wise':
            class_name = st.selectbox("Select CLASS", ['FE', 'SE', 'TE', 'BE'])

            if class_name:
                dept_names = ['auto', 'comps', 'ecs', 'extc', 'it', 'mech']  # Define department names
                sheets_dict = {}
                for dept_name in dept_names:
                    table_name = f"{dept_name}_{class_name.lower()}"
                    tables = fetch_year_institute_wise_tables(conn, table_name)
                    
                    st.write(f"Tables found for {table_name}: {tables}")  # Debug output
                    
                    if tables:
                        combined_data = []
                        for table in tables:
                            df = pd.read_sql(f"SELECT * FROM {table}", conn)
                            if not df.empty:
                                combined_data.append(df)
                        if combined_data:
                            combined_df = pd.concat(combined_data, ignore_index=True)
                            sheets_dict[dept_name] = combined_df

                if st.button("Export"):
                    if sheets_dict:
                        create_and_download_excel(sheets_dict, f"{class_name}_Year_Department_Wise")
                    else:
                        st.warning("No data found for the selected class and departments.")
                       
                       
        elif export_type == 'Individual':
            tables = fetch_all_tables(conn)

            # tables_df = pd.read_sql(
            #     "SELECT table_name FROM information_schema.tables WHERE table_schema = 'University3'", conn)
            # # Debugging output to check the returned DataFrame
            # st.write(tables_df)
            # tables = tables_df['TABLE_NAME'].tolist()  # Adjusted column name
            selected_table = st.selectbox("Select Table", tables)
            if selected_table and st.button("Export"):
                df = pd.read_sql(f"SELECT * FROM {selected_table}", conn)
                if not df.empty:
                    create_and_download_excel({'Sheet1': df}, selected_table)

        conn.close()
    else:
        st.error("Failed to connect to the database.")


if __name__ == "__main__":
    main()
