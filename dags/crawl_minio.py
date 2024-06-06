from airflow import DAG
from airflow.operators.python import PythonOperator
import datetime
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
import pandas as pd
from time import sleep
import logging
from bs4 import BeautifulSoup
from minio import Minio
from minio.error import S3Error
import io
import pandas as pd
from sqlalchemy import create_engine

minio_bucket = "ohitv"

client = Minio(
    "minio:9000",  # Replace with your MinIO server address
    access_key="minioadmin123",
    secret_key="minioadmin123",
    secure=False
    )

def crawl_data_feature():
    try:
        firefox_option = Options()
        firefox_option.add_argument("--headless")
        driver = webdriver.Remote(command_executor="http://selenium:4444/wd/hub",options=firefox_option)

        driver.get("https://ohitv.net/phim-le/page/1/")
        driver.fullscreen_window()
        sleep(5)

        page_html = driver.page_source
        soup = BeautifulSoup(page_html,"html.parser")
        elems_fea = soup.find_all("div",class_='data dfeatur')

        title = [elem.text for elem in elems_fea]
        links = []

        for div in elems_fea:
            href_element = div.find_all('a', href=True)

            for href in href_element:
                links.append(href['href'])

        data_fea = pd.DataFrame(list(zip(title,links)),columns=['title','link'])
        data_fea['feature'] = 'Yes'
        data_fea = data_fea.to_csv(index=False)

        try:
            # Check bucket exit or not
            if not client.bucket_exists(minio_bucket):
                client.make_bucket(minio_bucket)
            else:
                print(f"Bucket ohitv already exists")

            client.put_object(
                            bucket_name=minio_bucket, 
                            object_name="feature_film.csv",
                            data=io.BytesIO(data_fea.encode('utf-8')), 
                            length=len(data_fea)
            )

        except S3Error as e:
            print("Error occurred:", e)

    except Exception as e:
        logging.error("Error in Crawl data feature",e)
        raise

    finally:
        driver.quit()

def crawl_data_nofeature():
    try:
        firefox_option = Options()
        firefox_option.add_argument("--headless")
        driver = webdriver.Remote(command_executor="http://selenium:4444/wd/hub",options=firefox_option)

        data = pd.DataFrame(columns=['title','link'])
        kinds = ['phim-chieu-rap','action-adventure','phim-chinh-kich','phim-hai','phim-bi-an','phim-hinh-su','phim-gia-dinh',
                'phim-lang-man','phim-hanh-dong','phim-gia-tuong','sci-fi-fantasy','phim-phieu-luu','phim-hoat-hinh']

        title = []
        links = []

        for kind in kinds:
            for i in range(1,100):
                driver.get(f"https://ohitv.net/the-loai/{kind}/page/{i}/")
                driver.fullscreen_window()
                sleep(2)
                page_html = driver.page_source
                soup = BeautifulSoup(page_html,"html.parser")
                new_elems = soup.find_all("div",class_='data')
                if len(new_elems) == 0:
                    break
                else:

                    for name in new_elems:
                        title_element = name.find_all('h3')
                        for text in title_element:
                            title.append(text.text)

                    for div in new_elems:
                        href_element = div.find_all('a', href=True)
                        for href in href_element:
                            links.append(href['href'])

                new_data = pd.DataFrame(list(zip(title,links)),columns=['title','link'])
                new_data['kind'] = kind.replace('-',' ')
                data = pd.concat((data,new_data),axis=0,ignore_index=True)

        data['feature'] = 'No'
        data = data.to_csv(index=False)

        try:
            # Check if the bucket already exists
            if not client.bucket_exists(minio_bucket):
                client.make_bucket(minio_bucket)
            else:
                print(f"Bucket ohitv already exists")
            client.put_object(
                            bucket_name = minio_bucket, 
                            object_name = "nofeature_film.csv",
                            data = io.BytesIO(data.encode('utf-8')), 
                            length = len(data)
            )

        except S3Error as e:
            print("Error occurred:", e)

    except Exception as e:
        logging.error("No feature false",e)
        raise

    finally:
        driver.quit()

def processing_data():
    try:
        feature_object = client.get_object(minio_bucket,"Feature_Film.csv")
        feature_film = pd.read_csv(feature_object)

        nofeature_object = client.get_object(minio_bucket,"NoFeature_Film.csv")
        nofeature_film = pd.read_csv(nofeature_object)

        def return_feature(data):
            if data in feature_film['title'].to_list():
                return 'Yes'
            else:
                return 'No'

        nofeature_film['isfeature'] = nofeature_film['title'].apply(return_feature)
        new_data = nofeature_film.drop(columns='feature')
        new_data_nodup = new_data.drop_duplicates('title')

        new_data = new_data.to_csv(index=False)
        new_data_nodup = new_data_nodup.to_csv(index=False)

        client.put_object(minio_bucket,"duplicate_film.csv",io.BytesIO(new_data.encode('utf-8')), len(new_data))
        client.put_object(minio_bucket,"nodup_film.csv",io.BytesIO(new_data_nodup.encode('utf-8')), len(new_data_nodup))

    except Exception as e:
        logging.error("Cant Processing",e)
        raise

def backup_data():

    db_connection_string = "postgresql+psycopg2://airflow:airflow@postgres/backup"

    engine = create_engine(db_connection_string)

    csv_file = client.list_objects(minio_bucket, recursive=True)

    for csv in csv_file:
        file = client.get_object(minio_bucket,csv.object_name)
        df = pd.read_csv(file)
        table_name = csv.object_name.split('.')[0]
        df.to_sql(table_name, engine, if_exists='append', index=False)

default_args = {
    'owner': 'trieu',
    'start_date': datetime.datetime.now(),
    'retries': 1,
}

### Define the DAG ###
dag = DAG(
    dag_id='etl_ohitv_withbackup',
    default_args=default_args,
    schedule='@weekly',
)

no_fea = PythonOperator(
    task_id='nofea',
    python_callable=crawl_data_nofeature,
    dag=dag,
)

feature = PythonOperator(
    task_id='feature_crawl',
    python_callable=crawl_data_feature,
    dag=dag,
)

process = PythonOperator(
    task_id='process',
    python_callable=processing_data,
    dag=dag,
)

backup_fea = PythonOperator(
    task_id='backup_data_fea',
    python_callable=backup_data,
    dag=dag,
)

backup_nofea = PythonOperator(
    task_id='backup_data_nofea',
    python_callable=backup_data,
    dag=dag,
)

backup = PythonOperator(
    task_id='backup_data_final',
    python_callable=backup_data,
    dag=dag,
)

feature >> backup_fea >> no_fea >> backup_nofea >> process >> backup
