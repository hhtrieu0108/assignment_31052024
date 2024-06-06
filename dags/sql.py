from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import pandas as pd

class Postgre_Import:
    def __init__(self,database,uid,pwd,host,port):
        self.database = database
        self.uid = uid
        self.pwd = pwd
        self.host = host
        self.port = port
        self.conn = None
        self.columns = None
        self.table = None
    def connect_postgre_sql(self):
        import psycopg2
        conn = psycopg2.connect(dbname=self.database, user=self.uid, password=self.pwd, host=self.host, port=self.port)
        self.conn = conn
    def select_all(self,columns="*",table=any):
        import pandas as pd
        self.columns = columns
        self.table = table
        sql_query = f'SELECT {self.columns} FROM {self.table}'
        # Read the SQL query result into a DataFrame
        df = pd.read_sql(sql_query, self.conn)
        return df
    def post_pipeline(self):
        self.connect_postgre_sql()
        df = self.select_all(table='segment_result')
        return df
    def export_table(self,data,table_name):
        from sqlalchemy import create_engine
        if self.conn is None:
            self.connect_postgre_sql()
        # Sử dụng pandas để tạo bảng và nhập dữ liệu vào PostgreSQL
        engine = create_engine(f'postgresql+psycopg2://{self.uid}:{self.pwd}@{self.host}:{self.port}/{self.database}')
        data.to_sql(name=table_name, con=engine, index=False, if_exists='replace')
        print(f"Table '{table_name}' created and data imported successfully.")
    def close_connect(self):
        self.conn.close()

def query_function(): 
    psg = Postgre_Import(host='postgres',port='5432',uid='airflow',pwd='airflow',database='airflow')
    psg.connect_postgre_sql()
    df = psg.select_all(table='ab_user')
    df.to_csv('dags/airflow_user/airflow_abusers.csv', index=False)

default_args = {
    'owner': 'trieu',
    'start_date': datetime.now(),
    'retries': 1,
}

dag = DAG(
    'sql_query',
    default_args=default_args,
    schedule='@weekly',
)

query_task = PythonOperator(
    task_id='sql_query',
    python_callable=query_function,
    dag=dag,
)

query_task
