from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

def say_hello(**context):
    print(f"Hello from {context['ds']}")

with DAG(
    dag_id="hello_test",
    start_date=datetime(2024, 1, 1),
    schedule=None,  # <-- FIXED
    catchup=False,
) as dag:
    hello = PythonOperator(
        task_id="say_hello",
        python_callable=say_hello,
    )